from pathlib import Path
root=Path('/tmp/aurora-clean-ovmf/edk2')
p=root/'OvmfPkg/Library/PlatformBootManagerLib/BdsPlatform.c'
b=p.read_bytes()
start=b.index(b'  EFI_STATUS  Status;\r\n',b.index(b'DetectAndPreparePlatformPciDevicePath ('))
end=b.index(b'  //\r\n  // Here we decide whether it is LPC Bridge',start)
replacement='''  EFI_STATUS  Status;
  UINTN       Segment;
  UINTN       Bus;
  UINTN       Device;
  UINTN       Function;
  UINT16      Command;
  BOOLEAN     FixtureNvme;

  // This fixture has one namespace-free QEMU NVMe endpoint at 0000:00:02.0.
  // Generic PCI enumeration may previously have probed BME and restored it.
  // Do not mask an active controller by clearing an already-set BME bit.
  FixtureNvme = FALSE;
  if ((Pci->Hdr.VendorId == 0x1b36) &&
      (Pci->Hdr.DeviceId == 0x0010) &&
      (Pci->Hdr.ClassCode[2] == 0x01) &&
      (Pci->Hdr.ClassCode[1] == 0x08) &&
      (Pci->Hdr.ClassCode[0] == 0x02) &&
      (Pci->Hdr.HeaderType == 0x00))
  {
    Status = PciIo->GetLocation (PciIo, &Segment, &Bus, &Device, &Function);
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_ERROR, "AURORA_FIXTURE_FAIL: NVMe location: %r\\n", Status));
      CpuDeadLoop ();
      return Status;
    }

    FixtureNvme = (Segment == 0) && (Bus == 0) && (Device == 2) && (Function == 0);
  }

  if (FixtureNvme) {
    Status = PciIo->Pci.Read (
                          PciIo,
                          EfiPciIoWidthUint16,
                          PCI_COMMAND_OFFSET,
                          1,
                          &Command
                          );
    if (EFI_ERROR (Status) || ((Command & EFI_PCI_COMMAND_BUS_MASTER) != 0)) {
      DEBUG ((DEBUG_ERROR, "AURORA_FIXTURE_FAIL: initial command read/BME\\n"));
      CpuDeadLoop ();
      return EFI_DEVICE_ERROR;
    }

    DEBUG ((DEBUG_ERROR, "AURORA_FIXTURE_NVME: initial command=0x%04x\\n", Command));
    Status = PciIo->Attributes (
                      PciIo,
                      EfiPciIoAttributeOperationEnable,
                      EFI_PCI_IO_ATTRIBUTE_MEMORY,
                      NULL
                      );
    if (EFI_ERROR (Status)) {
      DEBUG ((DEBUG_ERROR, "AURORA_FIXTURE_FAIL: memory enable: %r\\n", Status));
      CpuDeadLoop ();
      return Status;
    }

    Status = PciIo->Pci.Read (
                          PciIo,
                          EfiPciIoWidthUint16,
                          PCI_COMMAND_OFFSET,
                          1,
                          &Command
                          );
    if (EFI_ERROR (Status) ||
        ((Command & (EFI_PCI_COMMAND_MEMORY_SPACE | EFI_PCI_COMMAND_BUS_MASTER)) !=
         EFI_PCI_COMMAND_MEMORY_SPACE))
    {
      DEBUG ((DEBUG_ERROR, "AURORA_FIXTURE_FAIL: final command read/MSE/BME\\n"));
      CpuDeadLoop ();
      return EFI_DEVICE_ERROR;
    }

    DEBUG ((DEBUG_ERROR, "AURORA_FIXTURE_NVME: 0000:00:02.0 command=0x%04x MSE=1 BME=0\\n", Command));
  } else {
    Status = PciIo->Attributes (
                      PciIo,
                      EfiPciIoAttributeOperationEnable,
                      EFI_PCI_DEVICE_ENABLE,
                      NULL
                      );
    ASSERT_EFI_ERROR (Status);
  }

'''.replace('\n','\r\n').encode()
p.write_bytes(b[:start]+replacement+b[end:])
for name in ['OvmfPkgX64.dsc','OvmfPkgX64.fdf']:
 p=root/'OvmfPkg'/name
 b=p.read_bytes()
 lines=b.splitlines(keepends=True)
 removed=[l for l in lines if b'NvmExpressDxe/NvmExpressDxe.inf' in l]
 assert len(removed)==1
 p.write_bytes(b''.join(l for l in lines if l not in removed))
