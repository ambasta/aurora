#!/usr/bin/env python3
"""Fixed BAR-preparation call-path bound using the existing compiler/ELF artifacts."""
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

spec = importlib.util.spec_from_file_location(
    'nvme_stack_frames', Path(__file__).with_name('kernel-uefi-ivrs-stack.py'))
frames = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frames)


def calculate(rows):
    def size(fragment, predicate=lambda name: True):
        found = [value for name, value in rows.items() if fragment in name and predicate(name)]
        if not found:
            raise ValueError('Missing preparation stack frame: ' + fragment)
        return max(found)

    payload = size('payload_main(')
    wrapper = size('discover_acpi(')
    acpi = size('prepare_bar_acpi(')
    topology = size('Topology::parse(')
    pci = size('discover_pci(')
    bar = size('inspect_bar(', lambda name: 'lambda' not in name)
    prepare = size('prepare_nvme_pages(')
    create = size('NvmeQueueBundle::prepare(')
    cancel = size('NvmeQueueBundle::cancel(')
    discard = size('NvmeQueueBundle::discard_unpublished(')
    scrub = size('NvmeQueueBundle::scrub_all(')
    page = size('NvmeQueueBundle::page(')
    verify = size('PageTables::verify(', lambda name: 'lambda' not in name)
    walk = size('PageTables::verify(', lambda name: 'lambda' in name)
    resource = size('PciResources::parse_as(')
    ecam = size('EcamWindow::read(')
    if payload > 512 or wrapper > 128 or acpi > 5120 or topology > 4096 or pci > 11000 or bar > 3072:
        raise ValueError('Reviewed preparation frame limit exceeded')
    if max(prepare, create, cancel, discard, scrub, page, verify, resource, ecam) > 1024 or walk > 128:
        raise ValueError('Reviewed preparation helper limit exceeded')
    modeled = ('payload_main(', 'discover_acpi(', 'prepare_bar_acpi(', 'Topology::parse(', 'discover_pci(',
               'inspect_bar(', 'prepare_nvme_pages(', 'NvmeQueueBundle::prepare(', 'NvmeQueueBundle::cancel(',
               'NvmeQueueBundle::discard_unpublished(', 'NvmeQueueBundle::scrub_all(', 'NvmeQueueBundle::page(',
               'PageTables::verify(', 'PciResources::parse_as(', 'EcamWindow::read(')
    if any(value < 0 or (value > 512 and not any(fragment in name for fragment in modeled))
           for name, value in rows.items()):
        raise ValueError('Unmodeled large preparation frame')
    # The four-level page-table walk is bounded by the existing verifier. 512
    # covers subordinate small callees; a separate 512 covers synchronous fault
    # delivery, stack alignment and the existing fail-stop serial diagnostics.
    leaf = 512
    fault = 512
    verifier = verify + 4 * walk
    queues = prepare + max(create, cancel) + discard + scrub + page
    paths = {
        'acpi': payload + wrapper + acpi + topology + leaf,
        'pci': payload + wrapper + pci + max(verifier, ecam) + leaf,
        'bar': payload + wrapper + pci + bar + max(queues, resource, verifier, ecam) + leaf,
    }
    peak = max(paths.values()) + fault
    if peak > 15360:
        raise ValueError('16 KiB preparation stack reserve exhausted')
    return dict(paths=paths, peak_with_fault_reserve=peak, fault_reserve=fault,
                stack_bytes=16384, minimum_unused=16384 - peak)


def linked_edges(disassembly):
    current = None
    edges = []
    for line in disassembly.splitlines():
        heading = re.match(r'^[0-9a-f]+ <(.+)>:$', line)
        if heading:
            current = heading[1]
        branch = re.search(r'\b(?:call|jmp)\s+[0-9a-f]+ <(.+)>', line)
        if current and branch:
            edges.append((current, branch[1]))
    if any('prepare_bar_acpi(' in caller and 'discover_pci(' in callee for caller, callee in edges):
        raise ValueError('ACPI parsing retains its frame through PCI discovery')
    for caller, callee in [('payload_main', 'discover_acpi('), ('discover_acpi(', 'prepare_bar_acpi('),
                           ('discover_acpi(', 'discover_pci('), ('discover_pci(', 'inspect_bar('),
                           ('inspect_bar(', 'prepare_nvme_pages('),
                           ('prepare_nvme_pages(', 'NvmeQueueBundle::prepare('),
                           ('prepare_nvme_pages(', 'NvmeQueueBundle::cancel(')]:
        if not any(caller in source and callee in target for source, target in edges):
            raise ValueError('Missing reviewed linked preparation edge: ' + caller + ' -> ' + callee)
    return edges


def self_test():
    rows = dict(zip(
        ('payload_main(', 'discover_acpi(', 'prepare_bar_acpi(', 'Topology::parse(', 'discover_pci(',
         'inspect_bar(', 'prepare_nvme_pages(', 'NvmeQueueBundle::prepare(', 'NvmeQueueBundle::cancel(',
         'NvmeQueueBundle::discard_unpublished(', 'NvmeQueueBundle::scrub_all(', 'NvmeQueueBundle::page(',
         'PageTables::verify(', 'PageTables::verify(lambda', 'PciResources::parse_as(', 'EcamWindow::read('),
        (240, 48, 3504, 3184, 10592, 2416, 208, 32, 32, 16, 72, 24, 208, 96, 640, 232)))
    if calculate(rows)['peak_with_fault_reserve'] != 14960:
        raise RuntimeError('Incorrect explicit preparation stack sum')
    rejected = 0
    for key in rows:
        for remove in (False, True):
            candidate = dict(rows)
            if remove:
                del candidate[key]
            else:
                candidate[key] = 32768
            try:
                calculate(candidate)
            except ValueError:
                rejected += 1
            else:
                raise RuntimeError('Invalid preparation frame accepted')
    try:
        calculate(dict(rows, unmodeled_subordinate=513))
    except ValueError:
        rejected += 1
    else:
        raise RuntimeError('Unmodeled large subordinate accepted')
    required = [('payload_main', 'discover_acpi('), ('discover_acpi(', 'prepare_bar_acpi('),
                ('discover_acpi(', 'discover_pci('), ('discover_pci(', 'inspect_bar('),
                ('inspect_bar(', 'prepare_nvme_pages('), ('prepare_nvme_pages(', 'NvmeQueueBundle::prepare('),
                ('prepare_nvme_pages(', 'NvmeQueueBundle::cancel(')]
    text = ''.join(f'100 <{caller}>:\n 100: call 200 <{callee}>\n' for caller, callee in required)
    linked_edges(text)
    for index in range(len(required)):
        candidate = ''.join(f'100 <{a}>:\n 100: call 200 <{b}>\n'
                            for at, (a, b) in enumerate(required) if at != index)
        try:
            linked_edges(candidate)
        except ValueError:
            rejected += 1
        else:
            raise RuntimeError('Missing linked preparation edge accepted')
    try:
        linked_edges(text + '100 <prepare_bar_acpi(>:\n 100: call 200 <discover_pci(>\n')
    except ValueError:
        rejected += 1
    else:
        raise RuntimeError('Nested ACPI lifetime accepted')
    print(f'PASS: preparation stack/frame/edge controls, 2 positives and {rejected} rejections')


if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    else:
        directory = Path(sys.argv[1])
        result = calculate(frames.load(directory))
        elf = directory / 'payload.elf'
        disassembly = subprocess.check_output(['objdump', '-drwC', str(elf)], text=True)
        edges = linked_edges(disassembly)
        result.update(payload_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(), linked_edges=len(edges))
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + '\n')
        print('PASS: bounded preparation stack paths ' + json.dumps(result, sort_keys=True))
