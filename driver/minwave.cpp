/*
 * VoiceMic Virtual Audio Device Driver
 * Wave Cyclic Miniport - Capture (microphone) implementation.
 *
 * Reads audio from shared memory ring buffer written by VoiceMic server app.
 * Presents it as a standard Windows capture audio device.
 */
#include "common.h"

#pragma code_seg("PAGE")

/* ── Wave format supported by our virtual mic ── */
static KSDATARANGE_AUDIO g_PinDataRangesCapture[] =
{
    {
        {
            sizeof(KSDATARANGE_AUDIO),
            0,
            0,
            0,
            STATICGUIDOF(KSDATAFORMAT_TYPE_AUDIO),
            STATICGUIDOF(KSDATAFORMAT_SUBTYPE_PCM),
            STATICGUIDOF(KSDATAFORMAT_SPECIFIER_WAVEFORMATEX)
        },
        2,      /* MaximumChannels */
        16,     /* MinimumBitsPerSample */
        16,     /* MaximumBitsPerSample */
        8000,   /* MinimumSampleFrequency */
        48000   /* MaximumSampleFrequency */
    }
};

static PKSDATARANGE g_PinDataRangePointersCapture[] =
{
    PKSDATARANGE(&g_PinDataRangesCapture[0])
};

/* ── Pin descriptor for capture pin ── */
static PCPIN_DESCRIPTOR g_MiniportPins[] =
{
    /* Pin 0: Capture (bridge - from shared memory) */
    {
        0, 0, 0,
        NULL,
        {
            0,
            NULL,
            0,
            NULL,
            SIZEOF_ARRAY(g_PinDataRangePointersCapture),
            g_PinDataRangePointersCapture,
            KSPIN_DATAFLOW_OUT,
            KSPIN_COMMUNICATION_SINK,
            NULL, NULL, NULL
        }
    }
};

/* ── Filter descriptor ── */
static PCFILTER_DESCRIPTOR g_FilterDescriptor =
{
    0,
    NULL,
    SIZEOF_ARRAY(g_MiniportPins),
    g_MiniportPins,
    0,
    NULL,
    0,
    NULL,
    0,
    NULL,
    NULL
};

/* ══════════════════════════════════════════════════
 * CMiniportWaveCyclic - The miniport implementation
 * ══════════════════════════════════════════════════ */

class CMiniportWaveCyclic :
    public IMiniportWaveCyclic,
    public CUnknown
{
private:
    PPORTWAVCYCLIC      m_pPort;
    PDEVICE_OBJECT      m_pDeviceObject;
    BOOL                m_fCaptureAllocated;

    /* Shared memory for audio data from the server app */
    HANDLE              m_hSection;
    PVOICEMIC_RING_BUFFER m_pRingBuffer;
    HANDLE              m_hEvent;

public:
    DECLARE_STD_UNKNOWN();
    DEFINE_STD_CONSTRUCTOR(CMiniportWaveCyclic);
    ~CMiniportWaveCyclic();

    IMP_IMiniportWaveCyclic;

    NTSTATUS OpenSharedMemory();
    void CloseSharedMemory();

    PVOICEMIC_RING_BUFFER GetRingBuffer() { return m_pRingBuffer; }
    BOOL IsServerActive() {
        return m_pRingBuffer && m_pRingBuffer->Active;
    }
};

/* ── Stream class ── */
class CMiniportWaveCyclicStream :
    public IMiniportWaveCyclicStream,
    public IDmaChannel,
    public CUnknown
{
private:
    CMiniportWaveCyclic *m_pMiniport;
    BOOL                m_fCapture;
    BOOL                m_fRunning;
    ULONG               m_ulDmaBufferSize;
    PVOID               m_pvDmaBuffer;
    ULONG               m_ulDmaPosition;

    /* Format */
    ULONG               m_ulSampleRate;
    ULONG               m_ulChannels;
    ULONG               m_ulBitsPerSample;
    ULONG               m_ulBytesPerSample;

public:
    DECLARE_STD_UNKNOWN();
    DEFINE_STD_CONSTRUCTOR(CMiniportWaveCyclicStream);
    ~CMiniportWaveCyclicStream();

    NTSTATUS Init(
        IN CMiniportWaveCyclic *pMiniport,
        IN ULONG Channel,
        IN BOOLEAN Capture,
        IN PKSDATAFORMAT DataFormat
    );

    /* IMiniportWaveCyclicStream */
    STDMETHODIMP_(NTSTATUS) SetFormat(IN PKSDATAFORMAT DataFormat);
    STDMETHODIMP_(ULONG) SetNotificationFreq(IN ULONG Interval, OUT PULONG FrameSize);
    STDMETHODIMP_(NTSTATUS) SetState(IN KSSTATE State);
    STDMETHODIMP_(NTSTATUS) GetPosition(OUT PULONG Position);
    STDMETHODIMP_(NTSTATUS) NormalizePhysicalPosition(IN OUT PLONGLONG PhysicalPosition);
    STDMETHODIMP_(void) Silence(IN PVOID Buffer, IN ULONG ByteCount);

    /* IDmaChannel */
    STDMETHODIMP_(ULONG) AllocatedBufferSize() { return m_ulDmaBufferSize; }
    STDMETHODIMP_(ULONG) BufferSize() { return m_ulDmaBufferSize; }
    STDMETHODIMP_(void) SetBufferSize(IN ULONG Size) { m_ulDmaBufferSize = Size; }
    STDMETHODIMP_(PVOID) SystemAddress() { return m_pvDmaBuffer; }
    STDMETHODIMP_(PHYSICAL_ADDRESS) PhysicalAddress();
    STDMETHODIMP_(void) CopyTo(IN PVOID Dest, IN PVOID Src, IN ULONG Bytes);
    STDMETHODIMP_(void) CopyFrom(IN PVOID Dest, IN PVOID Src, IN ULONG Bytes);

    void FillBufferFromSharedMemory();
};

/* ══════════════════════════════════════════
 * CMiniportWaveCyclic Implementation
 * ══════════════════════════════════════════ */

CMiniportWaveCyclic::CMiniportWaveCyclic(PUNKNOWN pUnkOuter)
    : CUnknown(pUnkOuter)
    , m_pPort(NULL)
    , m_pDeviceObject(NULL)
    , m_fCaptureAllocated(FALSE)
    , m_hSection(NULL)
    , m_pRingBuffer(NULL)
    , m_hEvent(NULL)
{
}

CMiniportWaveCyclic::~CMiniportWaveCyclic()
{
    PAGED_CODE();
    CloseSharedMemory();
    if (m_pPort) {
        m_pPort->Release();
        m_pPort = NULL;
    }
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclic::Init(
    IN PUNKNOWN         UnknownAdapter,
    IN PRESOURCELIST     ResourceList,
    IN PPORTWAVECYCLIC   Port
)
{
    PAGED_CODE();
    ASSERT(Port);

    m_pPort = Port;
    m_pPort->AddRef();

    /* Try to open shared memory from user-mode app */
    OpenSharedMemory();

    DPF(("[VoiceMic] MiniportWaveCyclic::Init OK\n"));
    return STATUS_SUCCESS;
}

NTSTATUS
CMiniportWaveCyclic::OpenSharedMemory()
{
    PAGED_CODE();
    NTSTATUS status;
    UNICODE_STRING sectionName;
    OBJECT_ATTRIBUTES oa;

    RtlInitUnicodeString(&sectionName, VOICEMIC_SHARED_MEM_NAME);
    InitializeObjectAttributes(&oa, &sectionName, OBJ_CASE_INSENSITIVE | OBJ_KERNEL_HANDLE, NULL, NULL);

    SIZE_T viewSize = RING_HEADER_SIZE + VOICEMIC_RING_BUFFER_SIZE;

    status = ZwOpenSection(&m_hSection, SECTION_MAP_READ | SECTION_MAP_WRITE, &oa);
    if (NT_SUCCESS(status)) {
        PVOID baseAddr = NULL;
        status = ZwMapViewOfSection(
            m_hSection, ZwCurrentProcess(), &baseAddr,
            0, 0, NULL, &viewSize, ViewUnmap, 0, PAGE_READWRITE
        );
        if (NT_SUCCESS(status)) {
            m_pRingBuffer = (PVOICEMIC_RING_BUFFER)baseAddr;
            DPF(("[VoiceMic] Shared memory mapped OK\n"));
        }
    } else {
        DPF(("[VoiceMic] Shared memory not yet available (app not running)\n"));
    }

    return status;
}

void
CMiniportWaveCyclic::CloseSharedMemory()
{
    PAGED_CODE();
    if (m_pRingBuffer) {
        ZwUnmapViewOfSection(ZwCurrentProcess(), m_pRingBuffer);
        m_pRingBuffer = NULL;
    }
    if (m_hSection) {
        ZwClose(m_hSection);
        m_hSection = NULL;
    }
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclic::GetDescription(
    OUT PPCFILTER_DESCRIPTOR *Description
)
{
    PAGED_CODE();
    ASSERT(Description);
    *Description = &g_FilterDescriptor;
    return STATUS_SUCCESS;
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclic::DataRangeIntersection(
    IN  ULONG           PinId,
    IN  PKSDATARANGE    ClientDataRange,
    IN  PKSDATARANGE    MyDataRange,
    IN  ULONG           OutputBufferLength,
    OUT PVOID           ResultantFormat OPTIONAL,
    OUT PULONG          ResultantFormatLength
)
{
    PAGED_CODE();
    return STATUS_NOT_IMPLEMENTED;
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclic::NewStream(
    OUT PMINIPORTWAVECYCLICSTREAM *Stream,
    IN  PUNKNOWN OuterUnknown OPTIONAL,
    IN  POOL_TYPE PoolType,
    IN  ULONG Pin,
    IN  BOOLEAN Capture,
    IN  PKSDATAFORMAT DataFormat,
    OUT PDMACHANNEL *DmaChannel,
    OUT PSERVICEGROUP *ServiceGroup
)
{
    PAGED_CODE();
    NTSTATUS status;

    DPF(("[VoiceMic] NewStream Pin=%d Capture=%d\n", Pin, Capture));

    /* Only support capture */
    if (!Capture) return STATUS_INVALID_PARAMETER;
    if (m_fCaptureAllocated) return STATUS_INSUFFICIENT_RESOURCES;

    CMiniportWaveCyclicStream *pStream = new(PoolType, VOICEMIC_POOLTAG)
        CMiniportWaveCyclicStream(OuterUnknown);
    if (!pStream) return STATUS_INSUFFICIENT_RESOURCES;

    pStream->AddRef();
    status = pStream->Init(this, Pin, Capture, DataFormat);
    if (NT_SUCCESS(status)) {
        *Stream = (PMINIPORTWAVECYCLICSTREAM)pStream;
        *DmaChannel = (PDMACHANNEL)pStream;
        (*DmaChannel)->AddRef();
        m_fCaptureAllocated = TRUE;

        /* Create a service group for timer-based callbacks */
        status = PcNewServiceGroup(ServiceGroup, NULL);
    }

    if (!NT_SUCCESS(status)) {
        pStream->Release();
    }

    return status;
}

/* ══════════════════════════════════════════
 * CMiniportWaveCyclicStream Implementation
 * ══════════════════════════════════════════ */

CMiniportWaveCyclicStream::CMiniportWaveCyclicStream(PUNKNOWN pUnkOuter)
    : CUnknown(pUnkOuter)
    , m_pMiniport(NULL)
    , m_fCapture(FALSE)
    , m_fRunning(FALSE)
    , m_ulDmaBufferSize(0)
    , m_pvDmaBuffer(NULL)
    , m_ulDmaPosition(0)
    , m_ulSampleRate(VOICEMIC_DEFAULT_SAMPLE_RATE)
    , m_ulChannels(VOICEMIC_DEFAULT_CHANNELS)
    , m_ulBitsPerSample(VOICEMIC_DEFAULT_BITS_PER_SAMPLE)
    , m_ulBytesPerSample(2)
{
}

CMiniportWaveCyclicStream::~CMiniportWaveCyclicStream()
{
    PAGED_CODE();
    if (m_pvDmaBuffer) {
        ExFreePoolWithTag(m_pvDmaBuffer, VOICEMIC_POOLTAG);
        m_pvDmaBuffer = NULL;
    }
}

NTSTATUS
CMiniportWaveCyclicStream::Init(
    IN CMiniportWaveCyclic *pMiniport,
    IN ULONG Channel,
    IN BOOLEAN Capture,
    IN PKSDATAFORMAT DataFormat
)
{
    PAGED_CODE();
    m_pMiniport = pMiniport;
    m_fCapture = Capture;

    /* Parse the data format */
    SetFormat(DataFormat);

    /* Allocate DMA buffer (10ms worth) */
    m_ulDmaBufferSize = (m_ulSampleRate * m_ulChannels * m_ulBytesPerSample) / 100;
    m_ulDmaBufferSize = max(m_ulDmaBufferSize, 4096);

    m_pvDmaBuffer = ExAllocatePool2(POOL_FLAG_NON_PAGED, m_ulDmaBufferSize, VOICEMIC_POOLTAG);
    if (!m_pvDmaBuffer) return STATUS_INSUFFICIENT_RESOURCES;

    RtlZeroMemory(m_pvDmaBuffer, m_ulDmaBufferSize);

    return STATUS_SUCCESS;
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclicStream::SetFormat(
    IN PKSDATAFORMAT DataFormat
)
{
    PAGED_CODE();
    if (DataFormat->FormatSize >= sizeof(KSDATAFORMAT_WAVEFORMATEX)) {
        PWAVEFORMATEX wfx = &((PKSDATAFORMAT_WAVEFORMATEX)DataFormat)->WaveFormatEx;
        m_ulSampleRate = wfx->nSamplesPerSec;
        m_ulChannels = wfx->nChannels;
        m_ulBitsPerSample = wfx->wBitsPerSample;
        m_ulBytesPerSample = m_ulBitsPerSample / 8;
    }
    return STATUS_SUCCESS;
}

STDMETHODIMP_(ULONG)
CMiniportWaveCyclicStream::SetNotificationFreq(
    IN  ULONG   Interval,
    OUT PULONG  FrameSize
)
{
    PAGED_CODE();
    /* Return bytes per ms * interval */
    ULONG bytesPerMs = (m_ulSampleRate * m_ulChannels * m_ulBytesPerSample) / 1000;
    *FrameSize = bytesPerMs * Interval;
    return Interval;
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclicStream::SetState(
    IN KSSTATE State
)
{
    PAGED_CODE();
    switch (State) {
        case KSSTATE_RUN:
            m_fRunning = TRUE;
            DPF(("[VoiceMic] Stream RUN\n"));
            break;
        case KSSTATE_PAUSE:
        case KSSTATE_ACQUIRE:
            m_fRunning = FALSE;
            break;
        case KSSTATE_STOP:
            m_fRunning = FALSE;
            m_ulDmaPosition = 0;
            DPF(("[VoiceMic] Stream STOP\n"));
            break;
    }
    return STATUS_SUCCESS;
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclicStream::GetPosition(
    OUT PULONG Position
)
{
    if (m_fRunning) {
        FillBufferFromSharedMemory();
    }
    *Position = m_ulDmaPosition;
    return STATUS_SUCCESS;
}

STDMETHODIMP_(NTSTATUS)
CMiniportWaveCyclicStream::NormalizePhysicalPosition(
    IN OUT PLONGLONG PhysicalPosition
)
{
    *PhysicalPosition = (*PhysicalPosition * m_ulSampleRate * m_ulChannels * m_ulBytesPerSample) / 10000000;
    return STATUS_SUCCESS;
}

STDMETHODIMP_(void)
CMiniportWaveCyclicStream::Silence(
    IN PVOID Buffer,
    IN ULONG ByteCount
)
{
    RtlZeroMemory(Buffer, ByteCount);
}

STDMETHODIMP_(PHYSICAL_ADDRESS)
CMiniportWaveCyclicStream::PhysicalAddress()
{
    PHYSICAL_ADDRESS pa;
    pa.QuadPart = 0;
    return pa;
}

STDMETHODIMP_(void)
CMiniportWaveCyclicStream::CopyTo(IN PVOID Dest, IN PVOID Src, IN ULONG Bytes)
{
    RtlCopyMemory(Dest, Src, Bytes);
}

STDMETHODIMP_(void)
CMiniportWaveCyclicStream::CopyFrom(IN PVOID Dest, IN PVOID Src, IN ULONG Bytes)
{
    RtlCopyMemory(Dest, Src, Bytes);
}

/*
 * Read audio data from shared memory ring buffer and fill DMA buffer.
 * If no data is available (server not running), fills with silence.
 */
void
CMiniportWaveCyclicStream::FillBufferFromSharedMemory()
{
    PVOICEMIC_RING_BUFFER pRing = m_pMiniport->GetRingBuffer();

    ULONG bytesToFill = m_ulDmaBufferSize;
    PBYTE pDest = (PBYTE)m_pvDmaBuffer;

    if (!pRing || !pRing->Active) {
        /* No server — output silence */
        RtlZeroMemory(pDest, bytesToFill);
        m_ulDmaPosition = (m_ulDmaPosition + bytesToFill) % m_ulDmaBufferSize;
        return;
    }

    /* Read from ring buffer */
    LONG readOff = pRing->ReadOffset;
    LONG writeOff = pRing->WriteOffset;
    LONG bufSize = pRing->BufferSize;

    if (bufSize <= 0) {
        RtlZeroMemory(pDest, bytesToFill);
        m_ulDmaPosition = (m_ulDmaPosition + bytesToFill) % m_ulDmaBufferSize;
        return;
    }

    LONG available = writeOff - readOff;
    if (available < 0) available += bufSize;

    ULONG toCopy = min((ULONG)available, bytesToFill);

    if (toCopy > 0) {
        /* Copy from ring buffer, handling wrap-around */
        LONG firstChunk = min(toCopy, (ULONG)(bufSize - (readOff % bufSize)));
        RtlCopyMemory(pDest, &pRing->Data[readOff % bufSize], firstChunk);

        if (toCopy > (ULONG)firstChunk) {
            RtlCopyMemory(pDest + firstChunk, &pRing->Data[0], toCopy - firstChunk);
        }

        /* Update read offset */
        InterlockedExchange(&pRing->ReadOffset, (readOff + toCopy) % bufSize);

        /* Fill remainder with silence if not enough data */
        if (toCopy < bytesToFill) {
            RtlZeroMemory(pDest + toCopy, bytesToFill - toCopy);
        }
    } else {
        RtlZeroMemory(pDest, bytesToFill);
    }

    m_ulDmaPosition = (m_ulDmaPosition + bytesToFill) % m_ulDmaBufferSize;
}

/* ── Factory ── */

#pragma code_seg("PAGE")
NTSTATUS
CreateMiniportWaveCyclic(
    OUT PUNKNOWN *Unknown,
    IN  REFCLSID,
    IN  PUNKNOWN UnkOuter OPTIONAL,
    IN  POOL_TYPE PoolType
)
{
    PAGED_CODE();
    ASSERT(Unknown);

    CMiniportWaveCyclic *p = new(PoolType, VOICEMIC_POOLTAG) CMiniportWaveCyclic(UnkOuter);
    if (!p) return STATUS_INSUFFICIENT_RESOURCES;

    *Unknown = PUNKNOWN((PMINIPORTWAVECYCLIC)p);
    (*Unknown)->AddRef();

    return STATUS_SUCCESS;
}
