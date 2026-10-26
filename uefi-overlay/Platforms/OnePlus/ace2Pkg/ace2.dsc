##
#  Copyright (c) 2011 - 2022, ARM Limited. All rights reserved.
#  Copyright (c) 2014, Linaro Limited. All rights reserved.
#  Copyright (c) 2015 - 2020, Intel Corporation. All rights reserved.
#  Copyright (c) 2018, Bingxing Wang. All rights reserved.
#  Copyright (c) Microsoft Corporation.
#
#  SPDX-License-Identifier: BSD-2-Clause-Patent
##

################################################################################
#
# Defines Section - statements that will be processed to create a Makefile.
#
################################################################################
[Defines]
  PLATFORM_NAME                  = ace2
  PLATFORM_GUID                  = 7E3D6F21-9B4C-4C58-9E7A-2F1C6A8D54B3
  PLATFORM_VERSION               = 0.1
  DSC_SPECIFICATION              = 0x00010005
  OUTPUT_DIRECTORY               = Build/ace2Pkg
  SUPPORTED_ARCHITECTURES        = AARCH64
  BUILD_TARGETS                  = RELEASE|DEBUG
  SKUID_IDENTIFIER               = DEFAULT
  FLASH_DEFINITION               = ace2Pkg/ace2.fdf
  USE_CUSTOM_DISPLAY_DRIVER      = 0

  #
  # 0 = SM8475
  # 1 = SM8475    (Overclocked)
  # 2 = SM7475-AB
  #
  SOC_TYPE                       = 0

!include PalimaPkg/PalimaPkg.dsc.inc

[PcdsFixedAtBuild]
  #
  # DDR Memory
  #
  gArmTokenSpaceGuid.PcdSystemMemoryBase|0x80000000

  #
  # UEFI Stack
  #
  gArmPlatformTokenSpaceGuid.PcdCPUCoresStackBase|0xA760D000
  gArmPlatformTokenSpaceGuid.PcdCPUCorePrimaryStackSize|0x40000

  #
  # SMBIOS
  #
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemManufacturer|"OnePlus"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemModel|"OnePlus Ace 2"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailModel|"ace2"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemRetailSku|"PHK110"
  gSiliciumPkgTokenSpaceGuid.PcdSmbiosSystemBoardModel|"PHK110"

  #
  # Simple Frame Buffer
  #
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferWidth|1240
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferHeight|2772
  gSiliciumPkgTokenSpaceGuid.PcdFrameBufferColorDepth|32

  #
  # Platform PEI
  #
  gQcomPkgTokenSpaceGuid.PcdPlatformType|"LA"

[LibraryClasses]
  #
  # Memory Libraries
  #
  MemoryMapLib|ace2Pkg/Library/MemoryMapLib/MemoryMapLib.inf

  #
  # QCOM Libraries
  #
  ConfigurationMapLib|ace2Pkg/Library/ConfigurationMapLib/ConfigurationMapLib.inf

[Components]
  DarwinBootPkg/Driver/DarwinBoot.inf
  ace2Pkg/Drivers/Ace2KeyInputDxe/Ace2KeyInputDxe.inf
  ace2Pkg/Drivers/ShengBootMemoryDxe/ShengBootMemoryDxe.inf
  ace2Pkg/Applications/Ace2MemDiag/Ace2MemDiag.inf
  #
  # ACPI Tables
  #
  pong/AcpiTables.inf
