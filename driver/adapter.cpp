/*
 * VoiceMic Virtual Audio Device Driver
 * Adapter initialization - entry point for the WDM audio miniport driver.
 *
 * Registers a virtual capture device (microphone) that reads audio
 * from shared memory written by the VoiceMic PC server.
 */
#include "common.h"

#pragma code_seg("INIT")

extern "C" DRIVER_INITIALIZE DriverEntry;

/* GUIDs for our miniports */
// {A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
DEFINE_GUID(CLSID_VoiceMicMiniportWave,
    0xa1b2c3d4, 0xe5f6, 0x7890, 0xab, 0xcd, 0xef, 0x12, 0x34, 0x56, 0x78, 0x90);

// {B2C3D4E5-F6A7-8901-BCDE-F12345678901}
DEFINE_GUID(CLSID_VoiceMicMiniportTopology,
    0xb2c3d4e5, 0xf6a7, 0x8901, 0xbc, 0xde, 0xf1, 0x23, 0x45, 0x67, 0x89, 0x01);

/* ── Port/Miniport pairs for our device ── */
static PCSUBDEVICE_DESCRIPTOR g_MiniportDescriptors[] =
{
    {
        0, NULL, NULL, NULL,
        &CLSID_VoiceMicMiniportWave,
        NULL, NULL, 0, NULL, 0, NULL
    }
};

#pragma code_seg("PAGE")

/*
 * AddDevice callback — called by PortCls to set up the adapter.
 */
NTSTATUS
AdapterCreate(
    IN  PDEVICE_OBJECT  DeviceObject,
    IN  PIRP            Irp,
    IN  PRESOURCELIST    ResourceList
)
{
    PAGED_CODE();
    NTSTATUS ntStatus;

    DPF(("[VoiceMic] AdapterCreate\n"));

    /* Create the wave miniport (capture) */
    PUNKNOWN pUnkMiniportWave = NULL;
    ntStatus = CreateMiniportWaveCyclic(
        &pUnkMiniportWave,
        CLSID_VoiceMicMiniportWave,
        NULL,
        NonPagedPoolNx
    );
    if (!NT_SUCCESS(ntStatus)) {
        DPF(("[VoiceMic] Failed to create wave miniport: 0x%08x\n", ntStatus));
        return ntStatus;
    }

    /* Create wave port */
    PUNKNOWN pUnkPort = NULL;
    ntStatus = PcNewPort(&pUnkPort, CLSID_PortWaveCyclic);
    if (!NT_SUCCESS(ntStatus)) {
        DPF(("[VoiceMic] Failed to create wave port: 0x%08x\n", ntStatus));
        pUnkMiniportWave->Release();
        return ntStatus;
    }

    /* Get IPort interface */
    PPORT pPort = NULL;
    ntStatus = pUnkPort->QueryInterface(IID_IPort, (PVOID*)&pPort);
    if (!NT_SUCCESS(ntStatus)) {
        pUnkPort->Release();
        pUnkMiniportWave->Release();
        return ntStatus;
    }

    /* Get IMiniport interface */
    PMINIPORT pMiniport = NULL;
    ntStatus = pUnkMiniportWave->QueryInterface(IID_IMiniport, (PVOID*)&pMiniport);
    if (!NT_SUCCESS(ntStatus)) {
        pPort->Release();
        pUnkPort->Release();
        pUnkMiniportWave->Release();
        return ntStatus;
    }

    /* Initialize the port with our miniport */
    ntStatus = pPort->Init(DeviceObject, Irp, pMiniport, NULL, ResourceList);
    if (!NT_SUCCESS(ntStatus)) {
        DPF(("[VoiceMic] Port init failed: 0x%08x\n", ntStatus));
    }

    /* Register as a subdevice */
    if (NT_SUCCESS(ntStatus)) {
        ntStatus = PcRegisterSubdevice(
            DeviceObject,
            L"VoiceMic",
            pUnkPort
        );
    }

    /* Cleanup */
    if (pMiniport) pMiniport->Release();
    if (pPort) pPort->Release();
    if (pUnkPort) pUnkPort->Release();
    if (pUnkMiniportWave) pUnkMiniportWave->Release();

    return ntStatus;
}

#pragma code_seg("INIT")

/*
 * DriverEntry — main driver entry point.
 */
extern "C"
NTSTATUS
DriverEntry(
    IN  PDRIVER_OBJECT  DriverObject,
    IN  PUNICODE_STRING RegistryPathName
)
{
    DPF(("[VoiceMic] DriverEntry\n"));

    /* Initialize PortCls */
    NTSTATUS ntStatus = PcInitializeAdapterDriver(
        DriverObject,
        RegistryPathName,
        (PDRIVER_ADD_DEVICE)AdapterCreate
    );

    return ntStatus;
}

#pragma code_seg()
