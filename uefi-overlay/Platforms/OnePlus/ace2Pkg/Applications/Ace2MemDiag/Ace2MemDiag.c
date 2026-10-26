/** @file
  Temporary bring-up diagnostic: print the live DT /memory banks on the panel.

  UniXNU renders its menu with GOP directly and does not route ConOut to the
  panel in graphics mode, so this app draws through GOP as well.

  SPDX-License-Identifier: BSD-2-Clause-Patent
**/

#include <Uefi.h>
#include <Pi/PiDxeCis.h>
#include <Pi/PiHob.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/FdtLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PrintLib.h>
#include <Library/UefiApplicationEntryPoint.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/GraphicsOutput.h>

#include "Internal.h"

#define MAX_RANGES  16

typedef struct {
  UINT64  Base;
  UINT64  End;
} RANGE;

STATIC CONST EFI_GRAPHICS_OUTPUT_BLT_PIXEL  mBg = { 0x0F, 0x0C, 0x0B, 0 };
STATIC CONST EFI_GRAPHICS_OUTPUT_BLT_PIXEL  mFg = { 0xF5, 0xF3, 0xF2, 0 };

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

STATIC
VOID
DrawLine (
  IN EFI_GRAPHICS_OUTPUT_PROTOCOL  *Gop,
  IN UINTN                         X,
  IN UINTN                         Y,
  IN CONST CHAR16                  *Text,
  IN UINTN                         Scale
  )
{
  UINTN                          Len;
  UINTN                          Cw;
  UINTN                          Ch;
  UINTN                          W;
  UINTN                          Index;
  UINTN                          Row;
  UINTN                          Col;
  UINTN                          Sy;
  UINTN                          Sx;
  UINTN                          Base;
  CHAR16                         C;
  CONST UINT8                    *Glyph;
  EFI_GRAPHICS_OUTPUT_BLT_PIXEL  *Buffer;

  if (Gop == NULL) {
    return;
  }

  Len = StrLen (Text);
  Cw  = UNIXNU_GLYPH_WIDTH * Scale;
  Ch  = UNIXNU_GLYPH_HEIGHT * Scale;
  if ((Len == 0) || (Y + Ch > Gop->Mode->Info->VerticalResolution)) {
    return;
  }

  Len = MIN (Len, (Gop->Mode->Info->HorizontalResolution - X) / Cw);
  W   = Len * Cw;
  if (W == 0) {
    return;
  }

  Buffer = AllocatePool (W * Ch * sizeof (*Buffer));
  if (Buffer == NULL) {
    return;
  }

  for (Index = 0; Index < W * Ch; Index++) {
    Buffer[Index] = mBg;
  }

  for (Index = 0; Index < Len; Index++) {
    C     = Text[Index];
    Glyph = gCaFontGlyphs[((C >= 0x20) && (C <= 0x7E)) ? (C - 0x20) : ('?' - 0x20)];
    for (Row = 0; Row < UNIXNU_GLYPH_HEIGHT; Row++) {
      for (Col = 0; Col < UNIXNU_GLYPH_WIDTH; Col++) {
        if ((Glyph[Row] & (0x80 >> Col)) == 0) {
          continue;
        }

        Base = (Row * Scale) * W + Index * Cw + Col * Scale;
        for (Sy = 0; Sy < Scale; Sy++) {
          for (Sx = 0; Sx < Scale; Sx++) {
            Buffer[Base + Sy * W + Sx] = mFg;
          }
        }
      }
    }
  }

  Gop->Blt (Gop, Buffer, EfiBltBufferToVideo, 0, 0, X, Y, W, Ch, 0);
  FreePool (Buffer);
}

EFI_STATUS
EFIAPI
UefiMain (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS                     Status;
  EFI_GRAPHICS_OUTPUT_PROTOCOL   *Gop;
  EFI_HOB_GUID_TYPE              *Hob;
  UINT64                         Dtb;
  CONST VOID                     *Fdt;
  INT32                          Root;
  INT32                          Node;
  INT32                          Length;
  CONST CHAR8                    *Type;
  UINT32                         AddressCells;
  UINT32                         SizeCells;
  RANGE                          Banks[MAX_RANGES];
  UINTN                          BankCount;
  UINTN                          Index;
  UINTN                          Y;
  CHAR16                         Line[160];

  Gop = NULL;
  Status = gBS->HandleProtocol (
                  gST->ConsoleOutHandle,
                  &gEfiGraphicsOutputProtocolGuid,
                  (VOID **)&Gop
                  );
  if (EFI_ERROR (Status)) {
    Status = gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&Gop);
    if (EFI_ERROR (Status)) {
      Gop = NULL;
    }
  }

  if (Gop != NULL) {
    Gop->Blt (
           Gop, (EFI_GRAPHICS_OUTPUT_BLT_PIXEL *)&mBg, EfiBltVideoFill,
           0, 0, 0, 0,
           Gop->Mode->Info->HorizontalResolution,
           Gop->Mode->Info->VerticalResolution,
           0
           );
  }

  Y = 40;
  Hob = GetFirstGuidHob (&gSiliciumEntryArgHobGuid);
  if (Hob == NULL) {
    DrawLine (Gop, 40, Y, L"Ace2MemDiag: no Silicium entry-argument HOB", 3);
    goto Wait;
  }

  Dtb = *(UINT64 *)GET_GUID_HOB_DATA (Hob);
  if ((Dtb == 0) || ((Dtb & 3) != 0) || (FdtCheckHeader ((VOID *)(UINTN)Dtb) != 0)) {
    UnicodeSPrint (Line, sizeof (Line), L"Ace2MemDiag: x0 %lx is not a valid DT", Dtb);
    DrawLine (Gop, 40, Y, Line, 3);
    goto Wait;
  }

  Fdt          = (CONST VOID *)(UINTN)Dtb;
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

  UnicodeSPrint (Line, sizeof (Line), L"Ace2MemDiag: DT %lx  banks %u  cells %u/%u",
                 Dtb, (UINT32)BankCount, AddressCells, SizeCells);
  DrawLine (Gop, 40, Y, Line, 3);
  Y += UNIXNU_GLYPH_HEIGHT * 3 + 20;

  for (Index = 0; Index < BankCount; Index++) {
    UnicodeSPrint (Line, sizeof (Line), L"MEM%u base %lx size %lx end %lx",
                   (UINT32)Index, (UINT64)Banks[Index].Base,
                   (UINT64)(Banks[Index].End - Banks[Index].Base),
                   (UINT64)Banks[Index].End);
    DrawLine (Gop, 40, Y, Line, 3);
    Y += UNIXNU_GLYPH_HEIGHT * 3 + 10;
  }

  DrawLine (Gop, 40, Y + 30, L"staying 180 s for photo", 3);

Wait:
  gBS->Stall (180000000);
  return EFI_SUCCESS;
}
