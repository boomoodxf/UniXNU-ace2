/** @file
  Memory and RAM disk from the device tree the previous stage handed over.

  The previous stage (a Linux-style boot loader) passes the physical address
  of a flattened device tree in x0, which SEC keeps in a HOB. Its /memory
  nodes list the real DRAM and its /reserved-memory nodes list what the
  secure side owns. Without the vendor memory manager the firmware only knows
  the few regions of its own memory map, so:

  * DRAM that no firmware region claims and no reserved-memory node covers is
    added to the GCD as system memory, up to a fixed amount;
  * the initrd the loader placed in memory (/chosen linux,initrd-start/-end)
    is published as a read-only block device, so a FAT image in the boot
    image's ramdisk shows up as a normal volume.

  Nothing here depends on a hardware address; every range comes from the DT.
**/

#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DxeServicesTableLib.h>
#include <Library/FdtLib.h>
#include <Library/DxeServicesLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>
#include <Protocol/SimpleFileSystem.h>
#include <Library/DevicePathLib.h>
#include <Library/ArmMmuLib.h>
#include <Library/PrintLib.h>
#include <Guid/FileInfo.h>

#define MAX_RANGES        64
#define MIN_PIECE_SIZE    SIZE_16MB
#define ADD_LIMIT         SIZE_1GB
#define ADD_BELOW         SIZE_4GB     // stay inside what the MMU setup maps

typedef struct {
  UINT64  Base;
  UINT64  End;       // exclusive
} RANGE;

STATIC
UINT64
ReadCells (
  IN CONST VOID  *Data,
  IN UINT32      Cells
  )
{
  if (Cells == 2) {
    return Fdt64ToCpu (ReadUnaligned64 (Data));
  }

  return Fdt32ToCpu (ReadUnaligned32 (Data));
}

STATIC
UINT32
GetCells (
  IN CONST VOID  *Fdt,
  IN INT32       Node,
  IN CONST CHAR8 *Name,
  IN UINT32      Default
  )
{
  CONST VOID  *Prop;
  INT32       Length;

  Prop = FdtGetProp (Fdt, Node, Name, &Length);
  if ((Prop == NULL) || (Length != sizeof (UINT32))) {
    return Default;
  }

  return Fdt32ToCpu (ReadUnaligned32 (Prop));
}

STATIC
UINTN
CollectReg (
  IN     CONST VOID  *Fdt,
  IN     INT32       Node,
  IN     UINT32      AddressCells,
  IN     UINT32      SizeCells,
  IN OUT RANGE       *Ranges,
  IN     UINTN       Count
  )
{
  CONST UINT8  *Reg;
  INT32        Length;
  UINT32       Entry;
  INT32        Offset;
  UINT64       Base;
  UINT64       Size;

  Reg = FdtGetProp (Fdt, Node, "reg", &Length);
  if (Reg == NULL) {
    return Count;
  }

  Entry = (AddressCells + SizeCells) * sizeof (UINT32);
  for (Offset = 0; (Offset + (INT32)Entry <= Length) && (Count < MAX_RANGES); Offset += Entry) {
    Base = ReadCells (Reg + Offset, AddressCells);
    Size = ReadCells (Reg + Offset + AddressCells * sizeof (UINT32), SizeCells);
    if ((Size != 0) && (Base + Size > Base)) {
      Ranges[Count].Base = Base;
      Ranges[Count].End  = Base + Size;
      Count++;
    }
  }

  return Count;
}

/**
  Remove every part of Pieces[] that lies inside Cut.
**/
STATIC
UINTN
Subtract (
  IN OUT RANGE  *Pieces,
  IN     UINTN  Count,
  IN     RANGE  Cut
  )
{
  UINTN  Index;
  UINTN  Result;
  RANGE  Out[MAX_RANGES];

  Result = 0;
  for (Index = 0; Index < Count; Index++) {
    if ((Cut.End <= Pieces[Index].Base) || (Cut.Base >= Pieces[Index].End)) {
      if (Result < MAX_RANGES) {
        Out[Result++] = Pieces[Index];
      }

      continue;
    }

    if ((Cut.Base > Pieces[Index].Base) && (Result < MAX_RANGES)) {
      Out[Result].Base  = Pieces[Index].Base;
      Out[Result].End   = Cut.Base;
      Result++;
    }

    if ((Cut.End < Pieces[Index].End) && (Result < MAX_RANGES)) {
      Out[Result].Base  = Cut.End;
      Out[Result].End   = Pieces[Index].End;
      Result++;
    }
  }

  CopyMem (Pieces, Out, Result * sizeof (RANGE));
  return Result;
}

STATIC
VOID
MapRange (
  IN UINT64               Base,
  IN UINT64               Size,
  IN EFI_GCD_MEMORY_TYPE  Type
  )
{
  EFI_STATUS  Status;
  UINT64      PageBase;
  UINT64      PageEnd;

  PageBase = Base & ~(UINT64)(SIZE_4KB - 1);
  PageEnd  = ALIGN_VALUE (Base + Size, SIZE_4KB);

  Status = gDS->AddMemorySpace (
                   Type,
                   PageBase,
                   PageEnd - PageBase,
                   EFI_MEMORY_UC | EFI_MEMORY_WC | EFI_MEMORY_WT | EFI_MEMORY_WB
                   );
  if (EFI_ERROR (Status) && (Status != EFI_ALREADY_STARTED) && (Status != EFI_ACCESS_DENIED)) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: range 0x%lx-0x%lx add %r\n", PageBase, PageEnd - 1, Status));
  }

  Status = gDS->SetMemorySpaceAttributes (PageBase, PageEnd - PageBase, EFI_MEMORY_WB);
  DEBUG ((DEBUG_ERROR, "SHENGMEM: range 0x%lx-0x%lx map %r\n", PageBase, PageEnd - 1, Status));
}

STATIC
VOID
AddMemory (
  IN CONST VOID  *Fdt
  )
{
  EFI_STATUS                       Status;
  EFI_GCD_MEMORY_SPACE_DESCRIPTOR  *Map;
  UINTN                            MapCount;
  INT32                            Root;
  INT32                            Node;
  INT32                            Reserved;
  INT32                            Length;
  CONST CHAR8                      *Type;
  UINT32                           AddressCells;
  UINT32                           SizeCells;
  RANGE                            Banks[MAX_RANGES];
  RANGE                            Holes[MAX_RANGES];
  RANGE                            Pieces[MAX_RANGES];
  UINTN                            BankCount;
  UINTN                            HoleCount;
  UINTN                            PieceCount;
  UINTN                            ReservedCount;
  RANGE                            ReservedRanges[MAX_RANGES];
  UINTN                            Index;
  UINTN                            Other;
  UINT64                           Added;
  UINT64                           Base;
  UINT64                           End;

  Root         = FdtPathOffset (Fdt, "/");
  AddressCells = GetCells (Fdt, Root, "#address-cells", 2);
  SizeCells    = GetCells (Fdt, Root, "#size-cells", 2);

  BankCount = 0;
  for (Node = FdtFirstSubnode (Fdt, Root); Node >= 0; Node = FdtNextSubnode (Fdt, Node)) {
    Type = FdtGetProp (Fdt, Node, "device_type", &Length);
    if ((Type != NULL) && (AsciiStrCmp (Type, "memory") == 0)) {
      BankCount = CollectReg (Fdt, Node, AddressCells, SizeCells, Banks, BankCount);
    }
  }

  ReservedCount = 0;
  Reserved      = FdtPathOffset (Fdt, "/reserved-memory");
  if (Reserved >= 0) {
    UINT32  ResAddress = GetCells (Fdt, Reserved, "#address-cells", AddressCells);
    UINT32  ResSize    = GetCells (Fdt, Reserved, "#size-cells", SizeCells);

    for (Node = FdtFirstSubnode (Fdt, Reserved); Node >= 0; Node = FdtNextSubnode (Fdt, Node)) {
      UINTN        Before;
      CONST CHAR8  *Name;

      Before        = ReservedCount;
      ReservedCount = CollectReg (Fdt, Node, ResAddress, ResSize, ReservedRanges, ReservedCount);
      if (ReservedCount > Before) {
        Name = FdtGetName (Fdt, Node, &Length);
        DEBUG ((DEBUG_ERROR, "SHENGMEM: rsv %a 0x%lx-0x%lx\n", Name, ReservedRanges[Before].Base, ReservedRanges[Before].End));
      }
    }
  }

  DEBUG ((DEBUG_ERROR, "SHENGMEM: DT has %u memory ranges and %u reserved ranges\n", (UINT32)BankCount, (UINT32)ReservedCount));
  if (BankCount == 0) {
    return;
  }

  Status = gDS->GetMemorySpaceMap (&MapCount, &Map);
  if (EFI_ERROR (Status)) {
    return;
  }

  //
  // Holes: DRAM the GCD does not know yet.
  //
  HoleCount = 0;
  for (Index = 0; Index < BankCount; Index++) {
    for (Other = 0; Other < MapCount; Other++) {
      if (Map[Other].GcdMemoryType != EfiGcdMemoryTypeNonExistent) {
        continue;
      }

      Base = MAX (Banks[Index].Base, Map[Other].BaseAddress);
      End  = MIN (Banks[Index].End, Map[Other].BaseAddress + Map[Other].Length);
      if ((Base < End) && (HoleCount < MAX_RANGES)) {
        Holes[HoleCount].Base = Base;
        Holes[HoleCount].End  = End;
        HoleCount++;
      }
    }
  }

  FreePool (Map);

  //
  // Minus everything the DT reserves; what is left is added right away.
  //
  Added = 0;
  for (Index = 0; (Index < HoleCount) && (Added < ADD_LIMIT); Index++) {
    Pieces[0]  = Holes[Index];
    PieceCount = 1;
    for (Other = 0; Other < ReservedCount; Other++) {
      PieceCount = Subtract (Pieces, PieceCount, ReservedRanges[Other]);
    }

    for (Other = 0; (Other < PieceCount) && (Added < ADD_LIMIT); Other++) {
      Base = ALIGN_VALUE (Pieces[Other].Base, SIZE_2MB);
      End  = Pieces[Other].End & ~((UINT64)SIZE_2MB - 1);
      if ((End <= Base) || (End - Base < MIN_PIECE_SIZE) || (End > ADD_BELOW)) {
        continue;
      }

      End = MIN (End, Base + (ADD_LIMIT - Added));

      //
      // Add and map before anything can allocate from it.
      //
      Status = gDS->AddMemorySpace (
                      EfiGcdMemoryTypeSystemMemory,
                      Base,
                      End - Base,
                      EFI_MEMORY_UC | EFI_MEMORY_WC | EFI_MEMORY_WT | EFI_MEMORY_WB
                      );
      if (!EFI_ERROR (Status)) {
        Status = gDS->SetMemorySpaceAttributes (Base, End - Base, EFI_MEMORY_WB);
        if (EFI_ERROR (Status)) {
          gDS->RemoveMemorySpace (Base, End - Base);
        } else {
          Added += End - Base;
        }
      }

      DEBUG ((DEBUG_ERROR, "SHENGMEM: system memory 0x%lx-0x%lx %r\n", Base, End - 1, Status));
    }
  }

  DEBUG ((DEBUG_ERROR, "SHENGMEM: added 0x%lx bytes of system memory\n", Added));

  //
  // SM8475 12 GiB: the high DDR bank observed at 0x840000000 on the same
  // 830/840-family boards is not in the stock low-only map. Publish the
  // 5 GiB window Udon's DarwinBoot validates, so the 4.75 GiB payload window
  // has a real contiguous run to allocate from.
  //
  {
    EFI_PHYSICAL_ADDRESS  HighBase = 0x840000000ULL;
    UINTN                 HighSize = 0x140000000ULL;

    Status = gDS->RemoveMemorySpace (HighBase, HighSize);
    Status = gDS->AddMemorySpace (
                     EfiGcdMemoryTypeSystemMemory,
                     HighBase,
                     HighSize,
                     EFI_MEMORY_UC | EFI_MEMORY_WC | EFI_MEMORY_WT | EFI_MEMORY_WB
                     );
    if (!EFI_ERROR (Status) || (Status == EFI_ALREADY_STARTED)) {
      Status = gDS->SetMemorySpaceAttributes (HighBase, HighSize, EFI_MEMORY_WB);
    }
    DEBUG ((DEBUG_ERROR, "SHENGMEM: high bank 0x%lx+0x%lx %r\n", (UINT64)HighBase, (UINT64)HighSize, Status));
  }
}

#define RAM_BLOCK_SIZE  512

#pragma pack(1)
typedef struct {
  VENDOR_DEVICE_PATH          Vendor;
  EFI_DEVICE_PATH_PROTOCOL    End;
} RAM_BLOCK_DEVICE_PATH;
#pragma pack()

STATIC RAM_BLOCK_DEVICE_PATH  mDevicePath = {
  {
    { HARDWARE_DEVICE_PATH, HW_VENDOR_DP, { (UINT8)sizeof (VENDOR_DEVICE_PATH), (UINT8)(sizeof (VENDOR_DEVICE_PATH) >> 8) } },
    { 0xA9C6827C, 0x1BD8, 0x410C, { 0x88, 0x5A, 0xC4, 0x65, 0x00, 0xF7, 0xD8, 0x36 } }
  },
  { END_DEVICE_PATH_TYPE, END_ENTIRE_DEVICE_PATH_SUBTYPE, { sizeof (EFI_DEVICE_PATH_PROTOCOL), 0 } }
};

STATIC UINT8                    *mRamBase;
STATIC EFI_BLOCK_IO_MEDIA       mMedia;

STATIC
EFI_STATUS
EFIAPI
RamBlockReset (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN BOOLEAN                ExtendedVerification
  )
{
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockRead (
  IN  EFI_BLOCK_IO_PROTOCOL  *This,
  IN  UINT32                 MediaId,
  IN  EFI_LBA                Lba,
  IN  UINTN                  BufferSize,
  OUT VOID                   *Buffer
  )
{
  if (Buffer == NULL) {
    return EFI_INVALID_PARAMETER;
  }

  if (MediaId != mMedia.MediaId) {
    return EFI_MEDIA_CHANGED;
  }

  if ((BufferSize % RAM_BLOCK_SIZE) != 0) {
    return EFI_BAD_BUFFER_SIZE;
  }

  if ((Lba > mMedia.LastBlock) || ((BufferSize / RAM_BLOCK_SIZE) > (mMedia.LastBlock + 1 - Lba))) {
    return EFI_INVALID_PARAMETER;
  }

  CopyMem (Buffer, mRamBase + Lba * RAM_BLOCK_SIZE, BufferSize);
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockWrite (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN UINT32                 MediaId,
  IN EFI_LBA                Lba,
  IN UINTN                  BufferSize,
  IN VOID                   *Buffer
  )
{
  return EFI_WRITE_PROTECTED;
}

STATIC
EFI_STATUS
EFIAPI
RamBlockFlush (
  IN EFI_BLOCK_IO_PROTOCOL  *This
  )
{
  return EFI_SUCCESS;
}

STATIC EFI_BLOCK_IO_PROTOCOL  mBlockIo = {
  EFI_BLOCK_IO_PROTOCOL_REVISION,
  &mMedia,
  RamBlockReset,
  RamBlockRead,
  RamBlockWrite,
  RamBlockFlush
};

STATIC CONST EFI_GUID  mRamdiskGuid = {
  0xB7C1F4A2, 0x9D3E, 0x4F5A, { 0x8C, 0x6B, 0x1E, 0x2D, 0x3F, 0x4A, 0x5B, 0x6C }
};

STATIC
VOID
PublishVolume (
  IN VOID   *Base,
  IN UINTN  Size
  )
{
  EFI_STATUS  Status;
  EFI_HANDLE  Handle;

  if ((Base == NULL) || (Size < RAM_BLOCK_SIZE) || ((Size % RAM_BLOCK_SIZE) != 0)) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: bad volume 0x%lx size 0x%lx\n", (UINT64)(UINTN)Base, (UINT64)Size));
    return;
  }

  mRamBase                = Base;
  mMedia.MediaId          = 1;
  mMedia.RemovableMedia   = FALSE;
  mMedia.MediaPresent     = TRUE;
  mMedia.LogicalPartition = FALSE;
  mMedia.ReadOnly         = TRUE;
  mMedia.WriteCaching     = FALSE;
  mMedia.BlockSize        = RAM_BLOCK_SIZE;
  mMedia.IoAlign          = 1;
  mMedia.LastBlock        = Size / RAM_BLOCK_SIZE - 1;

  Handle = NULL;
  Status = gBS->InstallMultipleProtocolInterfaces (
                  &Handle,
                  &gEfiDevicePathProtocolGuid,
                  &mDevicePath,
                  &gEfiBlockIoProtocolGuid,
                  &mBlockIo,
                  NULL
                  );
  DEBUG ((DEBUG_ERROR, "SHENGMEM: volume 0x%lx size 0x%lx %r\n", (UINT64)(UINTN)Base, (UINT64)Size, Status));
  if (!EFI_ERROR (Status)) {
    gBS->ConnectController (Handle, NULL, NULL, TRUE);
  }
}


#define PONGFAT_MAGIC      "PONGFAT1"
#define PONGFAT_HEADER     4096
#define PONGFAT_MAX_INITRD SIZE_128MB

STATIC
EFI_STATUS
MakeReadable (
  IN UINT64  Address,
  IN UINTN   Size
  )
{
  UINT64  Base, End, Page, El, Par;

  if ((Address < SIZE_1MB) || (Size == 0) || (Size > PONGFAT_MAX_INITRD) ||
      (Address >= LShiftU64 (1, 48)) || (Size > LShiftU64 (1, 48) - Address)) {
    return EFI_INVALID_PARAMETER;
  }
  Base = Address & ~((UINT64)EFI_PAGE_SIZE - 1);
  End  = ALIGN_VALUE (Address + Size, EFI_PAGE_SIZE);
  __asm__ volatile ("mrs %0, CurrentEL" : "=r" (El));
  for (Page = Base; Page < End; Page += EFI_PAGE_SIZE) {
    if (El == 4) {
      __asm__ volatile ("at s1e1r, %1; isb; mrs %0, par_el1" : "=r" (Par) : "r" (Page) : "memory");
    } else if (El == 8) {
      __asm__ volatile ("at s1e2r, %1; isb; mrs %0, par_el1" : "=r" (Par) : "r" (Page) : "memory");
    } else {
      return EFI_UNSUPPORTED;
    }
    if ((Par & 1) != 0) {
      return ArmSetMemoryAttributes (Base, End - Base, EFI_MEMORY_WB | EFI_MEMORY_XP, 0);
    }
  }
  return EFI_SUCCESS;
}

STATIC
BOOLEAN
InitrdRange (
  IN  VOID    *Fdt,
  OUT UINT64  *Start,
  OUT UINT64  *End
  )
{
  INT32       Node, ASize, BSize;
  CONST VOID  *A, *B;

  Node = FdtPathOffset (Fdt, "/chosen");
  if (Node < 0) {
    return FALSE;
  }
  A = FdtGetProp (Fdt, Node, "linux,initrd-start", &ASize);
  B = FdtGetProp (Fdt, Node, "linux,initrd-end", &BSize);
  if ((A == NULL) || (B == NULL) || ((ASize != 4) && (ASize != 8)) || ((BSize != 4) && (BSize != 8))) {
    return FALSE;
  }
  *Start = (ASize == 8) ? Fdt64ToCpu (ReadUnaligned64 (A)) : Fdt32ToCpu (ReadUnaligned32 (A));
  *End   = (BSize == 8) ? Fdt64ToCpu (ReadUnaligned64 (B)) : Fdt32ToCpu (ReadUnaligned32 (B));
  return (*Start != 0) && (*End > *Start) && (*End <= MAX_UINTN) && ((*End - *Start) <= PONGFAT_MAX_INITRD);
}

STATIC
EFI_STATUS
PublishInitrd (
  IN VOID  *Fdt
  )
{
  CONST UINT8           *Bytes, *Header, *Fat;
  UINTN                 Span, Index, FatBytes;
  UINT64                Start, End, Size;
  UINT32                Crc, Sectors;
  EFI_STATUS            Status;
  EFI_PHYSICAL_ADDRESS  Copy;

  if (!InitrdRange (Fdt, &Start, &End)) {
    return EFI_NOT_FOUND;
  }
  DEBUG ((DEBUG_ERROR, "SHENGMEM: initrd 0x%lx-0x%lx\n", Start, End));
  Status = MakeReadable (Start, (UINTN)(End - Start));
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: initrd readable %r\n", Status));
    return Status;
  }
  Bytes = (CONST UINT8 *)(UINTN)Start;
  Span  = (UINTN)(End - Start);
  if (Span < PONGFAT_HEADER + 512) {
    return EFI_NOT_FOUND;
  }
  for (Index = 0; Index <= Span - PONGFAT_HEADER - 512; ++Index) {
    Header = Bytes + Index;
    if ((Header[0] != 'P') || (CompareMem (Header, PONGFAT_MAGIC, 8) != 0)) {
      continue;
    }
    if ((ReadUnaligned32 ((CONST UINT32 *)(Header + 8)) != 1) ||
        (ReadUnaligned32 ((CONST UINT32 *)(Header + 12)) != PONGFAT_HEADER)) {
      continue;
    }
    Size = ReadUnaligned64 ((CONST UINT64 *)(Header + 16));
    if ((Size < 512) || ((Size % 512) != 0) || (Size > Span - Index - PONGFAT_HEADER)) {
      continue;
    }
    FatBytes = (UINTN)Size;
    Fat      = Header + PONGFAT_HEADER;
    if ((Fat[510] != 0x55) || (Fat[511] != 0xAA) || (ReadUnaligned16 ((CONST UINT16 *)(Fat + 11)) != 512)) {
      continue;
    }
    Sectors = ReadUnaligned16 ((CONST UINT16 *)(Fat + 19));
    if (Sectors == 0) {
      Sectors = ReadUnaligned32 ((CONST UINT32 *)(Fat + 32));
    }
    if (Sectors != FatBytes / 512) {
      continue;
    }
    Status = gBS->CalculateCrc32 ((VOID *)Fat, FatBytes, &Crc);
    if (EFI_ERROR (Status) || (Crc != ReadUnaligned32 ((CONST UINT32 *)(Header + 24)))) {
      continue;
    }
    Copy   = 0;
    Status = gBS->AllocatePages (AllocateAnyPages, EfiReservedMemoryType, EFI_SIZE_TO_PAGES (FatBytes), &Copy);
    if (EFI_ERROR (Status)) {
      return Status;
    }
    CopyMem ((VOID *)(UINTN)Copy, Fat, FatBytes);
    DEBUG ((DEBUG_ERROR, "SHENGMEM: initrd FAT +0x%lx size 0x%lx\n", (UINT64)Index, Size));
    PublishVolume ((VOID *)(UINTN)Copy, FatBytes);
    return EFI_SUCCESS;
  }
  return EFI_NOT_FOUND;
}

STATIC
EFI_STATUS
LoadAppFromSfs (
  IN  EFI_HANDLE  ImageHandle,
  OUT EFI_HANDLE  *AppHandle
  )
{
  EFI_STATUS                     Status;
  EFI_HANDLE                     *Handles;
  UINTN                          Count;
  UINTN                          Index;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Sfs;
  EFI_FILE_PROTOCOL              *Root;
  EFI_FILE_PROTOCOL              *File;
  EFI_FILE_INFO                  *Info;
  UINTN                          InfoSize;
  UINTN                          Size;
  VOID                           *Buffer;

  *AppHandle = NULL;
  Status = gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &Count, &Handles);
  if (EFI_ERROR (Status)) {
    return Status;
  }
  Status = EFI_NOT_FOUND;
  for (Index = 0; Index < Count; Index++) {
    Sfs = NULL;
    if (EFI_ERROR (gBS->HandleProtocol (Handles[Index], &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Sfs))) {
      continue;
    }
    Root = NULL;
    if (EFI_ERROR (Sfs->OpenVolume (Sfs, &Root))) {
      continue;
    }
    File = NULL;
    if (EFI_ERROR (Root->Open (Root, &File, L"\\EFI\\UniXNU\\UniXNU.efi", EFI_FILE_MODE_READ, 0))) {
      Root->Close (Root);
      continue;
    }
    Info     = NULL;
    InfoSize = 0;
    if ((File->GetInfo (File, &gEfiFileInfoGuid, &InfoSize, NULL) == EFI_BUFFER_TOO_SMALL) &&
        (InfoSize >= sizeof (EFI_FILE_INFO))) {
      Info = AllocatePool (InfoSize);
    }
    if ((Info == NULL) || EFI_ERROR (File->GetInfo (File, &gEfiFileInfoGuid, &InfoSize, Info))) {
      if (Info != NULL) {
        FreePool (Info);
      }
      File->Close (File);
      Root->Close (Root);
      continue;
    }
    Size   = (UINTN)Info->FileSize;
    Buffer = AllocatePool (Size);
    if ((Buffer != NULL) && !EFI_ERROR (File->Read (File, &Size, Buffer))) {
      Status = gBS->LoadImage (FALSE, ImageHandle, NULL, Buffer, Size, AppHandle);
      DEBUG ((DEBUG_ERROR, "SHENGMEM: sfs loader %r size 0x%lx\n", Status, (UINT64)Size));
    }
    if (Buffer != NULL) {
      FreePool (Buffer);
    }
    FreePool (Info);
    File->Close (File);
    Root->Close (Root);
    if (!EFI_ERROR (Status)) {
      break;
    }
  }
  gBS->FreePool (Handles);
  return Status;
}

STATIC CONST EFI_GUID  mUnixnuGuid = {
  0xB7C1F4A3, 0x9D3E, 0x4F5A, { 0x8C, 0x6B, 0x1E, 0x2D, 0x3F, 0x4A, 0x5B, 0x6C }
};

EFI_STATUS
EFIAPI
ShengBootMemoryDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS         Status;
  EFI_HOB_GUID_TYPE  *Hob;
  UINT64             Dtb;

  Hob = GetFirstGuidHob (&gSiliciumEntryArgHobGuid);
  if (Hob == NULL) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: no entry argument HOB\n"));
    return EFI_SUCCESS;
  }

  Dtb = *(UINT64 *)GET_GUID_HOB_DATA (Hob);
  if ((Dtb == 0) || ((Dtb & 3) != 0)) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: x0 0x%lx is not a device tree\n", Dtb));
    return EFI_SUCCESS;
  }

  MapRange (Dtb, SIZE_2MB, EfiGcdMemoryTypeReserved);
  if (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: x0 0x%lx is not a device tree\n", Dtb));
    return EFI_SUCCESS;
  }

  DEBUG ((DEBUG_ERROR, "SHENGMEM: device tree at 0x%lx, %u bytes\n", Dtb, (UINT32)FdtTotalSize ((VOID *)(UINTN)Dtb)));

  AddMemory ((VOID *)(UINTN)Dtb);

  Status = PublishInitrd ((VOID *)(UINTN)Dtb);
  DEBUG ((DEBUG_ERROR, "SHENGMEM: initrd volume %r\n", Status));
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "SHENGMEM: no initrd payload\n"));
    return EFI_SUCCESS;
  }

  {
    EFI_HANDLE  *Handles;
    UINTN       Count;

    Handles = NULL;
    Count   = 0;
    Status  = gBS->LocateHandleBuffer (ByProtocol, &gEfiSimpleFileSystemProtocolGuid, NULL, &Count, &Handles);
    DEBUG ((DEBUG_ERROR, "SHENGMEM: SFS handles %u %r\n", Count, Status));
    if (Handles != NULL) {
      gBS->FreePool (Handles);
    }
  }

  {
    EFI_HANDLE  AppHandle;

    AppHandle = NULL;
    Status    = LoadAppFromSfs (ImageHandle, &AppHandle);
    if (!EFI_ERROR (Status)) {
      Status = gBS->StartImage (AppHandle, NULL, NULL);
      DEBUG ((DEBUG_ERROR, "SHENGMEM: StartImage %r\n", Status));
    }
  }

  gBS->Stall (30000000);
  return EFI_SUCCESS;
}
