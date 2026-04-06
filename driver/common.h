/*
 * VoiceMic Virtual Audio Device Driver
 * Common definitions and structures
 *
 * This driver registers a virtual capture (microphone) device
 * that reads audio from a shared memory ring buffer written by
 * the VoiceMic PC server application.
 */
#pragma once

#include <ntddk.h>
#include <portcls.h>
#include <stdunk.h>
#include <ksdebug.h>
#include <ntddk.h>

/* ── Shared Memory ── */
#define VOICEMIC_SHARED_MEM_NAME    L"\\BaseNamedObjects\\VoiceMicAudioBuffer"
#define VOICEMIC_EVENT_NAME         L"\\BaseNamedObjects\\VoiceMicAudioEvent"
#define VOICEMIC_RING_BUFFER_SIZE   (48000 * 2 * 2)  /* 1 sec stereo 16-bit */

/* ── Audio Format Defaults ── */
#define VOICEMIC_DEFAULT_SAMPLE_RATE     48000
#define VOICEMIC_DEFAULT_CHANNELS        1
#define VOICEMIC_DEFAULT_BITS_PER_SAMPLE 16
#define VOICEMIC_MIN_SAMPLE_RATE         8000
#define VOICEMIC_MAX_SAMPLE_RATE         48000

/* ── Device IDs ── */
#define VOICEMIC_DEVICE_MAX_INSTANCES    1

/* Ring buffer header in shared memory */
typedef struct _VOICEMIC_RING_BUFFER {
    volatile LONG   WriteOffset;
    volatile LONG   ReadOffset;
    volatile LONG   SampleRate;
    volatile LONG   Channels;
    volatile LONG   BitsPerSample;
    volatile LONG   Active;         /* 1 = server is streaming */
    LONG            BufferSize;
    LONG            Reserved[9];    /* pad to 64 bytes */
    BYTE            Data[1];        /* ring buffer data follows */
} VOICEMIC_RING_BUFFER, *PVOICEMIC_RING_BUFFER;

#define RING_HEADER_SIZE  64

/* ── Driver Tags ── */
#define VOICEMIC_POOLTAG   'cMiV'

/* ── Debug ── */
#if DBG
#define DPF(x) DbgPrint x
#else
#define DPF(x)
#endif

/* ── Forward Declarations ── */
NTSTATUS CreateMiniportWaveCyclic(
    OUT PUNKNOWN *Unknown,
    IN  REFCLSID ClassID,
    IN  PUNKNOWN UnkOuter OPTIONAL,
    IN  POOL_TYPE PoolType
);

NTSTATUS CreateMiniportTopology(
    OUT PUNKNOWN *Unknown,
    IN  REFCLSID ClassID,
    IN  PUNKNOWN UnkOuter OPTIONAL,
    IN  POOL_TYPE PoolType
);

NTSTATUS PropertyHandler_CpuResources(
    IN PPCPROPERTY_REQUEST PropertyRequest
);
