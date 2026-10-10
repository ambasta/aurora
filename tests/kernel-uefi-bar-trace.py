#!/usr/bin/env python3
"""Trace receipts for one pinned QEMU 10.0.13 namespace-free q35 fixture.

No universal DMA tracer is claimed. DMA inactivity is constrained by reset,
no controller initialization, no queue/doorbell writes, and zero retained state.
The separate stock and MSI-X controls are intentionally active coverage evidence.
"""

from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys

spec = importlib.util.spec_from_file_location("bar_smoke", Path(__file__).with_name("kernel-uefi-bar-smoke.py"))
bar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bar)
need = bar.need
MEMORY = re.compile(
    (
        "memory_region_ops_write cpu (-?[0-9]+) mr 0x([0-9a-f]+) addr 0x([0-9a-f]+) value 0x([0-9a-f]+) size (["
        "0-9]+) name '([^']+)'"
    )
)
PCI = re.compile(
    r"pci_cfg_(read|write) ([^ ]+) ([0-9a-f]{2}):([0-9a-f]{2})\.([0-7]) @0x([0-9a-f]+) (->|<-) 0x([0-9a-f]+)"
)
MMIO = re.compile(r"pci_nvme_mmio_read addr 0x([0-9a-f]+) size ([0-9]+)")
RESET = "pci_nvme_pci_reset PCI Function Level Reset"
FIRMWARE_MARKERS = [
    "AURORA_FIXTURE_NVME: initial command=0x0000",
    "AURORA_FIXTURE_NVME: 0000:00:02.0 command=0x0002 MSE=1 BME=0",
    "AURORA_FIXTURE_NVME: initial command=0x0002",
    "AURORA_FIXTURE_NVME: 0000:00:02.0 command=0x0002 MSE=1 BME=0",
]
# Exact installed-binary event inventory, independently captured with -trace help.
# Updating this pin requires rechecking source coverage and both real controls.
EVENT_TEXT = (
    "pci_nvme_irq_msix\npci_nvme_irq_pin\npci_nvme_irq_masked\npci_nvme_dma_read\npci_nvme_dbbuf_config\npci_nv"
    "me_map_addr\npci_nvme_map_addr_cmb\npci_nvme_map_prp\npci_nvme_map_sgl\npci_nvme_io_cmd\npci_nvme_admin_cm"
    "d\npci_nvme_flush_ns\npci_nvme_format_set\npci_nvme_read\npci_nvme_write\npci_nvme_rw_cb\npci_nvme_misc_cb"
    "\npci_nvme_dif_rw\npci_nvme_dif_rw_cb\npci_nvme_dif_rw_mdata_in_cb\npci_nvme_dif_rw_mdata_out_cb\npci_nvme"
    "_dif_rw_check_cb\npci_nvme_dif_pract_generate_dif_crc16\npci_nvme_dif_pract_generate_dif_crc64\npci_nvme_d"
    "if_check\npci_nvme_dif_prchk_disabled_crc16\npci_nvme_dif_prchk_disabled_crc64\npci_nvme_dif_prchk_guard_c"
    "rc16\npci_nvme_dif_prchk_guard_crc64\npci_nvme_dif_prchk_apptag\npci_nvme_dif_prchk_reftag_crc16\npci_nvme"
    "_dif_prchk_reftag_crc64\npci_nvme_copy\npci_nvme_copy_source_range\npci_nvme_copy_out\npci_nvme_verify\npc"
    "i_nvme_verify_mdata_in_cb\npci_nvme_verify_cb\npci_nvme_rw_complete_cb\npci_nvme_block_status\npci_nvme_ds"
    "m\npci_nvme_dsm_deallocate\npci_nvme_dsm_single_range_limit_exceeded\npci_nvme_compare\npci_nvme_compare_d"
    "ata_cb\npci_nvme_compare_mdata_cb\npci_nvme_aio_discard_cb\npci_nvme_aio_copy_in_cb\npci_nvme_aio_flush_cb"
    "\npci_nvme_create_sq\npci_nvme_create_cq\npci_nvme_del_sq\npci_nvme_del_cq\npci_nvme_identify\npci_nvme_id"
    "entify_ctrl\npci_nvme_identify_ctrl_csi\npci_nvme_identify_ns\npci_nvme_identify_ns_ind\npci_nvme_identify"
    "_ctrl_list\npci_nvme_identify_pri_ctrl_cap\npci_nvme_identify_sec_ctrl_list\npci_nvme_identify_ns_csi\npci"
    "_nvme_identify_nslist\npci_nvme_identify_nslist_csi\npci_nvme_identify_cmd_set\npci_nvme_identify_ns_descr"
    "_list\npci_nvme_get_log\npci_nvme_getfeat\npci_nvme_setfeat\npci_nvme_getfeat_vwcache\npci_nvme_getfeat_nu"
    "mq\npci_nvme_setfeat_numq\npci_nvme_setfeat_timestamp\npci_nvme_getfeat_timestamp\npci_nvme_process_aers\n"
    "pci_nvme_aer\npci_nvme_aer_aerl_exceeded\npci_nvme_aer_masked\npci_nvme_aer_post_cqe\npci_nvme_ns_attachme"
    "nt\npci_nvme_ns_attachment_attach\npci_nvme_enqueue_event\npci_nvme_enqueue_event_noqueue\npci_nvme_enqueu"
    "e_event_masked\npci_nvme_no_outstanding_aers\npci_nvme_enqueue_req_completion\npci_nvme_update_cq_eventidx"
    "\npci_nvme_update_sq_eventidx\npci_nvme_mmio_read\npci_nvme_mmio_write\npci_nvme_mmio_doorbell_cq\npci_nvm"
    "e_mmio_doorbell_sq\npci_nvme_mmio_intm_set\npci_nvme_mmio_intm_clr\npci_nvme_mmio_cfg\npci_nvme_mmio_aqatt"
    "r\npci_nvme_mmio_asqaddr\npci_nvme_mmio_acqaddr\npci_nvme_mmio_asqaddr_hi\npci_nvme_mmio_acqaddr_hi\npci_n"
    "vme_mmio_start_success\npci_nvme_mmio_stopped\npci_nvme_mmio_shutdown_set\npci_nvme_mmio_shutdown_cleared"
    "\npci_nvme_update_cq_head\npci_nvme_update_sq_tail\npci_nvme_open_zone\npci_nvme_close_zone\npci_nvme_fini"
    "sh_zone\npci_nvme_reset_zone\npci_nvme_zns_zone_reset\npci_nvme_offline_zone\npci_nvme_set_descriptor_exte"
    "nsion\npci_nvme_zd_extension_set\npci_nvme_clear_ns_close\npci_nvme_clear_ns_reset\npci_nvme_zoned_zrwa_im"
    "plicit_flush\npci_nvme_pci_reset\npci_nvme_virt_mngmt\npci_nvme_fdp_ruh_change\npci_nvme_err_mdts\npci_nvm"
    "e_err_zasl\npci_nvme_err_req_status\npci_nvme_err_addr_read\npci_nvme_err_addr_write\npci_nvme_err_cfs\npc"
    "i_nvme_err_aio\npci_nvme_err_copy_invalid_format\npci_nvme_err_invalid_sgld\npci_nvme_err_invalid_num_sgld"
    "\npci_nvme_err_invalid_sgl_excess_length\npci_nvme_err_invalid_dma\npci_nvme_err_invalid_prplist_ent\npci_"
    "nvme_err_invalid_prp2_align\npci_nvme_err_invalid_opc\npci_nvme_err_invalid_admin_opc\npci_nvme_err_invali"
    "d_lba_range\npci_nvme_err_invalid_log_page_offset\npci_nvme_err_cmb_invalid_cba\npci_nvme_err_cmb_not_enab"
    "led\npci_nvme_err_unaligned_zone_cmd\npci_nvme_err_invalid_zone_state_transition\npci_nvme_err_write_not_a"
    "t_wp\npci_nvme_err_append_not_at_start\npci_nvme_err_zone_is_full\npci_nvme_err_zone_is_read_only\npci_nvm"
    "e_err_zone_is_offline\npci_nvme_err_zone_boundary\npci_nvme_err_zone_invalid_write\npci_nvme_err_zone_writ"
    "e_not_ok\npci_nvme_err_zone_read_not_ok\npci_nvme_err_insuff_active_res\npci_nvme_err_insuff_open_res\npci"
    "_nvme_err_zd_extension_map_error\npci_nvme_err_invalid_iocsci\npci_nvme_err_invalid_del_sq\npci_nvme_err_i"
    "nvalid_create_sq_cqid\npci_nvme_err_invalid_create_sq_sqid\npci_nvme_err_invalid_create_sq_size\npci_nvme_"
    "err_invalid_create_sq_addr\npci_nvme_err_invalid_create_sq_qflags\npci_nvme_err_invalid_del_cq_cqid\npci_n"
    "vme_err_invalid_del_cq_notempty\npci_nvme_err_invalid_create_cq_cqid\npci_nvme_err_invalid_create_cq_size"
    "\npci_nvme_err_invalid_create_cq_addr\npci_nvme_err_invalid_create_cq_vector\npci_nvme_err_invalid_create_"
    "cq_qflags\npci_nvme_err_invalid_create_cq_entry_size\npci_nvme_err_invalid_identify_cns\npci_nvme_err_inva"
    "lid_getfeat\npci_nvme_err_invalid_setfeat\npci_nvme_err_invalid_log_page\npci_nvme_err_startfail_cq\npci_n"
    "vme_err_startfail_sq\npci_nvme_err_startfail_asq_misaligned\npci_nvme_err_startfail_acq_misaligned\npci_nv"
    "me_err_startfail_page_too_small\npci_nvme_err_startfail_page_too_large\npci_nvme_err_startfail_cqent_too_s"
    "mall\npci_nvme_err_startfail_cqent_too_large\npci_nvme_err_startfail_sqent_too_small\npci_nvme_err_startfa"
    "il_sqent_too_large\npci_nvme_err_startfail_css\npci_nvme_err_startfail_asqent_sz_zero\npci_nvme_err_startf"
    "ail_acqent_sz_zero\npci_nvme_err_startfail_zasl_too_small\npci_nvme_err_startfail\npci_nvme_err_startfail_"
    "virt_state\npci_nvme_err_invalid_mgmt_action\npci_nvme_err_ignored_mmio_vf_offline\npci_nvme_ub_mmiowr_mis"
    "aligned32\npci_nvme_ub_mmiowr_toosmall\npci_nvme_ub_mmiowr_intmask_with_msix\npci_nvme_ub_mmiowr_ro_csts\n"
    "pci_nvme_ub_mmiowr_ssreset_w1c_unsupported\npci_nvme_ub_mmiowr_ssreset_unsupported\npci_nvme_ub_mmiowr_cmb"
    "loc_reserved\npci_nvme_ub_mmiowr_cmbsz_readonly\npci_nvme_ub_mmiowr_pmrcap_readonly\npci_nvme_ub_mmiowr_pm"
    "rsts_readonly\npci_nvme_ub_mmiowr_pmrebs_readonly\npci_nvme_ub_mmiowr_pmrswtp_readonly\npci_nvme_ub_mmiowr"
    "_invalid\npci_nvme_ub_mmiord_misaligned32\npci_nvme_ub_mmiord_toosmall\npci_nvme_ub_mmiord_invalid_ofs\npc"
    "i_nvme_ub_db_wr_misaligned\npci_nvme_ub_db_wr_invalid_cq\npci_nvme_ub_db_wr_invalid_cqhead\npci_nvme_ub_db"
    "_wr_invalid_sq\npci_nvme_ub_db_wr_invalid_sqtail\npci_nvme_ub_unknown_css_value\npci_nvme_ub_too_many_mapp"
    "ings\npci_cfg_read\npci_cfg_write\nmsix_write_config\nmemory_region_ops_write\n"
)
EVENTS = frozenset(EVENT_TEXT.splitlines())


def normalized(text):
    return text.replace("\r\n", "\n")


def parse_trace(text):
    need(isinstance(text, str) and text.endswith("\n"), "Missing/truncated hardware trace")
    records, serial, debug = [], [], []
    serial_at, debug_at = [], []
    lcr = 0  # QEMU cold-reset 16550 state, before firmware writes LCR.
    for index, line in enumerate(text.splitlines()):
        name = line.split(" ", 1)[0]
        need(name in EVENTS, "Unknown/uncovered/malformed trace event: " + name)
        record = {"name": name, "line": line, "index": index}
        if name == "memory_region_ops_write":
            match = MEMORY.fullmatch(line)
            need(match is not None, "Malformed memory-region write")
            cpu, mr, address, value, size, region = match.groups()
            cpu, mr, address, value, size = int(cpu), int(mr, 16), int(address, 16), int(value, 16), int(size)
            need(
                -1 <= cpu <= 0
                and size in (1, 2, 4, 8)
                and value < 1 << (size * 8)
                and 0 <= address < 1 << 64
                and size <= (1 << 64) - address,
                "Invalid write CPU/address/width/value",
            )
            record.update(cpu=cpu, mr=mr, address=address, value=value, size=size, region=region)
            if region == "serial" and 0x3F8 <= address <= 0x3FF:
                need(size == 1, "Unexpected COM1 register width")
                if address == 0x3FB:
                    lcr = value
                elif address == 0x3F8 and not lcr & 0x80:
                    serial.append(chr(value))
                    serial_at.append(index)
            if region == "isa-debugcon":
                need(address == 0x402 and size == 1, "Foreign firmware debug port")
                debug.append(chr(value))
                debug_at.append(index)
        elif name.startswith("pci_cfg_"):
            match = PCI.fullmatch(line)
            need(match is not None, "Malformed PCI configuration event")
            operation, device, bus, slot, function, offset, arrow, value = match.groups()
            need(arrow == ("->" if operation == "read" else "<-"), "Wrong config direction")
            bdf = tuple(int(v, 16) for v in (bus, slot, function))
            need(bdf[1] < 32 and int(offset, 16) < 4096 and int(value, 16) <= 0xFFFFFFFF, "Invalid PCI event bounds")
            if device == "nvme" or bdf == (0, 2, 0):
                need(device == "nvme" and bdf == (0, 2, 0), "Foreign/additional NVMe endpoint")
            record.update(operation=operation, device=device, bdf=bdf, offset=int(offset, 16), value=int(value, 16))
        elif name == "pci_nvme_mmio_read":
            match = MMIO.fullmatch(line)
            need(match is not None, "Malformed NVMe read")
            record.update(address=int(match[1], 16), size=int(match[2]))
        elif name == "pci_nvme_pci_reset":
            need(line == RESET, "Malformed initial reset")
        elif name == "msix_write_config":
            need(
                re.fullmatch(r"msix_write_config dev [^ ]+ enabled [01] masked [01]", line),
                "Malformed MSI-X config event",
            )
        else:
            need(" " in line and line.split(" ", 1)[1] != "", "Truncated NVMe event")
        records.append(record)
    return records, "".join(serial), serial_at, "".join(debug), debug_at


def marker_index(stream, positions, marker):
    at = stream.find(marker)
    need(at >= 0 and stream.find(marker, at + 1) < 0, "Missing/duplicate trace marker " + marker)
    return positions[at], positions[at + len(marker) - 1]


def validate_stock_control(text, require_state=True):
    records, serial, positions, _, _ = parse_trace(text)
    entry, _ = marker_index(serial, positions, "AURORA_UEFI_ENTRY")
    before = [r for r in records if r["index"] < entry]
    resets = [r for r in records if r["name"] == "pci_nvme_pci_reset"]
    need(len(resets) == 1 and resets[0]["index"] < 8, "Stock control lacks cold reset")
    required = {
        "pci_nvme_mmio_cfg",
        "pci_nvme_mmio_aqattr",
        "pci_nvme_mmio_asqaddr",
        "pci_nvme_mmio_acqaddr",
        "pci_nvme_mmio_start_success",
        "pci_nvme_mmio_doorbell_sq",
        "pci_nvme_mmio_doorbell_cq",
        "pci_nvme_create_sq",
        "pci_nvme_create_cq",
        "pci_nvme_irq_pin",
    }
    need(
        required <= {r["name"] for r in before},
        "Stock control lacks real initialization/queue/doorbell/interrupt coverage",
    )
    writes = [r for r in before if r["name"] == "memory_region_ops_write" and r["region"] == "nvme"]
    need(
        writes and any(r["value"] == 0x460001 and r["size"] == 4 for r in writes), "Stock generic write coverage absent"
    )
    if require_state:
        need("cc=4587521 csts=1 aqa=65537" in serial, "Stock measured initialization missing")
    return len(writes)


def read_control(directory):
    path = Path(directory)
    need(path.is_dir(), "MSI-X control directory unavailable")
    names = (
        "SHA256SUMS",
        "invocation.json",
        "protocol.jsonl",
        "result.json",
        "trace.log",
        "trace-verification.json",
        "qtest-native.log",
        "query-pci.json",
        "qtree.txt",
        "stderr.log",
        "control.py",
        "verify-trace.py",
    )
    return {name: (path / name).read_bytes().decode("utf-8") for name in names}


def verify_msix_control(artifacts):
    need(isinstance(artifacts, dict), "Missing real MSI-X coverage artifacts")
    manifest = {}
    for line in artifacts.get("SHA256SUMS", "").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9_.-]+)", line)
        need(match and match[2] not in manifest, "Malformed/duplicate control digest")
        manifest[match[2]] = match[1]
    required = {
        "invocation.json",
        "protocol.jsonl",
        "result.json",
        "trace.log",
        "trace-verification.json",
        "qtest-native.log",
        "query-pci.json",
        "qtree.txt",
        "stderr.log",
        "control.py",
        "verify-trace.py",
    }
    need(required == set(manifest) and required <= set(artifacts), "Incomplete MSI-X provenance")
    for name in required:
        need(
            hashlib.sha256(artifacts[name].encode()).hexdigest() == manifest[name],
            "MSI-X artifact digest mismatch: " + name,
        )
    need(artifacts["stderr.log"] == "", "MSI-X control reported process errors")
    invocation = json.loads(artifacts["invocation.json"])
    argv = invocation["argv"]
    need(
        "-S" in argv
        and "-nodefaults" in argv
        and "-drive" not in argv
        and "-blockdev" not in argv
        and argv.count("-device") == 1,
        "MSI-X control was not stopped/namespace-free",
    )
    device = argv[argv.index("-device") + 1]
    need(
        device.startswith("nvme,") and "bus=pcie.0,addr=02.0" in device and "drive=" not in device,
        "Wrong MSI-X control device",
    )
    records, serial, _, debug, _ = parse_trace(artifacts["trace.log"])
    need(not serial and not debug, "Stopped control executed firmware")
    need(
        all(r["device"] == "nvme" and r["bdf"] == (0, 2, 0) for r in records if r["name"] == "pci_cfg_write"),
        "Control wrote a foreign PCI endpoint",
    )
    writes = [(r["offset"], r["value"]) for r in records if r["name"] == "pci_cfg_write"]
    need(writes == [(0x10, 0xC0000004), (0x14, 0), (4, 2)], "Unexpected control PCI writes")
    allowed = {"pci_nvme_pci_reset", "pci_nvme_mmio_read"}
    need(all(r["name"] in allowed for r in records if r["name"].startswith("pci_nvme_")), "Control initialized NVMe")
    tables = [r for r in records if r["name"] == "memory_region_ops_write" and r["region"] == "msix-table"]
    need(
        len(tables) == 1
        and (tables[0]["cpu"], tables[0]["address"], tables[0]["value"], tables[0]["size"]) == (-1, 0xC000200C, 1, 4),
        "Real same-value masked MSI-X table write absent",
    )
    need(
        not any(
            r["name"] == "msix_write_config"
            or (r["name"] == "memory_region_ops_write" and r["region"] in ("nvme", "msix-pba"))
            for r in records
        ),
        "Control enabled MSI-X/controller",
    )
    protocol = [json.loads(line) for line in artifacts["protocol.jsonl"].splitlines()]
    greeting = protocol[0].get("data", {}).get("QMP", {}).get("version", {}).get("qemu")
    need(
        protocol[0]["kind"] == "qmp-greeting" and greeting == {"major": 10, "minor": 0, "micro": 13},
        "Control binary version mismatch",
    )
    qtest, statuses, blocks, qmp_commands, pci_queries, qtrees = [], [], [], [], [], []
    i = 1
    while i < len(protocol):
        request = protocol[i]
        need(i + 1 < len(protocol), "Truncated control protocol")
        response = protocol[i + 1]
        kind = request["kind"]
        data = request["data"]
        need(
            kind in ("qmp-request", "qtest-request") and response["kind"] == kind.replace("request", "response"),
            "Unpaired control protocol",
        )
        if kind == "qmp-request":
            operation = data.get("execute")
            qmp_commands.append(operation)
            need(
                operation in ("qmp_capabilities", "query-status", "query-block", "query-pci", "human-monitor-command")
                and "return" in response["data"],
                "Unapproved/failed QMP control operation",
            )
            value = response["data"]["return"]
            if operation == "query-status":
                statuses.append(value)
            if operation == "query-block":
                blocks.append(value)
            if operation == "query-pci":
                pci_queries.append(value)
            if operation == "human-monitor-command":
                need(data.get("arguments") == {"command-line": "info qtree"}, "Unexpected HMP control mutation")
                qtrees.append(value)
        else:
            need(isinstance(response["data"], str) and response["data"].startswith("OK"), "Failed qtest access")
            qtest.append((data, response["data"]))
        i += 2
    need(
        len(statuses) == 2
        and all(s.get("running") is False and s.get("status") == "prelaunch" for s in statuses)
        and blocks == [[]],
        "Control CPUs ran or backing blocks existed",
    )
    need(
        pci_queries == [json.loads(artifacts["query-pci.json"])] and qtrees == [artifacts["qtree.txt"]],
        "QMP raw/saved identity snapshots differ",
    )
    targets = [
        (bus.get("bus"), device)
        for bus in pci_queries[0]
        for device in bus.get("devices", [])
        if device.get("id", {}).get("vendor") == 0x1B36 and device.get("id", {}).get("device") == 0x10
    ]
    need(
        len(targets) == 1
        and targets[0][0] == 0
        and targets[0][1].get("slot") == 2
        and targets[0][1].get("function") == 0,
        "Control identity/topology mismatch",
    )
    native = []
    for line in artifacts["qtest-native.log"].splitlines():
        match = re.fullmatch(r"\[([RSI]) [^\]]+\] (.*)", line)
        need(match is not None, "Malformed native qtest log")
        if match[1] != "I":
            native.append((match[1], match[2]))
        else:
            need(match[2] in ("OPENED", "CLOSED"), "Unexpected native qtest lifecycle")
    need(
        native == [(kind, value) for request, response in qtest for kind, value in (("R", request), ("S", response))],
        "Native qtest/protocol logs disagree",
    )
    selector = None
    config_writes = []
    config_reads = []
    mmio_reads = []
    mmio_writes = []
    for request, response in qtest:
        parts = request.split()
        operation = parts[0]
        need(operation in ("outl", "outw", "inb", "inl", "inw", "readl", "writel"), "Unknown control access")
        address = int(parts[1], 16)
        if operation == "outl" and address == 0xCF8:
            selector = int(parts[2], 16)
            need(selector & 0xFFFFFF00 == 0x80001000, "Control selected foreign device")
        elif operation in ("outl", "outw"):
            need(selector is not None and 0xCFC <= address <= 0xCFF, "Foreign control port write")
            config_writes.append(((selector & 255) + address - 0xCFC, int(parts[2], 16)))
        elif operation in ("inb", "inl", "inw"):
            need(selector is not None and 0xCFC <= address <= 0xCFF, "Foreign control port read")
            config_reads.append(((selector & 255) + address - 0xCFC, int(response.split()[1], 16)))
        elif operation == "readl":
            mmio_reads.append((address, int(response.split()[1], 16)))
        else:
            mmio_writes.append((address, int(parts[2], 16)))
    need(config_writes == writes and mmio_writes == [(0xC000200C, 1)], "Protocol/trace write mismatch")
    need(
        config_reads == [(r["offset"], r["value"]) for r in records if r["name"] == "pci_cfg_read"],
        "Protocol/trace config readbacks disagree",
    )
    need(
        [(o, v) for o, v in config_reads if o in (0, 8, 0xE, 0x34, 0x40, 0x44)]
        == [(0, 0x101B36), (8, 0x1080202), (0xE, 0), (0x34, 0x40), (0x40, 0x11), (0x44, 0x2000)],
        "Control identity/capability readbacks disagree",
    )
    need(
        [v & 0xFFFF for o, v in config_reads if o == 4] == [0, 2, 2]
        and [v for o, v in config_reads if o == 0x42] == [0x40, 0x40, 0x40],
        "Command/MSI-X control readback mismatch",
    )
    need([v for a, v in mmio_reads if a == 0xC000200C] == [1, 1], "MSI-X mask readback mismatch")
    expected = [(0xC0000000 + off, 0) for off in (0x14, 0x1C, 0x24, 0x28, 0x2C, 0x30, 0x34)]
    need([(a, v) for a, v in mmio_reads if a != 0xC000200C] == expected * 2, "Controller/queue readbacks not all zero")
    need(
        [(r["address"], r["size"]) for r in records if r["name"] == "pci_nvme_mmio_read"]
        == [(a - 0xC0000000, 4) for a, _ in expected * 2],
        "Protocol/trace controller read counts differ",
    )
    result = json.loads(artifacts["result.json"])
    need(
        result.get("control_passed") is True
        and result.get("cpu_running") is False
        and result.get("namespace_backends") == []
        and result.get("bdf") == "0000:00:02.0"
        and result.get("vendor_device") == "1b36:0010",
        "Control summary disagrees",
    )
    return {"table_write": [0xC000200C, 1, 4], "cpu_stopped": True}


def validate_coverage(coverage):
    need(isinstance(coverage, dict) and coverage.get("qemu_version") == "10.0.13", "Unpinned trace binary")
    enabled = coverage.get("events", "").splitlines()
    available = set(coverage.get("available_events", "").splitlines())
    need(
        len(enabled) == 218 and len(set(enabled)) == 218 and set(enabled) == EVENTS,
        "Incomplete/unreviewed enabled trace inventory",
    )
    relevant = {e for e in available if e.startswith("pci_nvme_")} | {
        "pci_cfg_read",
        "pci_cfg_write",
        "msix_write_config",
        "memory_region_ops_write",
    }
    need(relevant == EVENTS and EVENTS <= available, "Binary trace inventory differs from coverage contract")
    control = (
        read_control(coverage["msix_control"])
        if isinstance(coverage.get("msix_control"), str)
        else coverage.get("msix_control")
    )
    msix = verify_msix_control(control)
    stock_writes = validate_stock_control(coverage.get("stock_trace", ""))
    return {"msix_control": msix, "stock_controller_writes": stock_writes}


def expected_config_writes(base):
    probe = [(4, 0), (0x10, 0xFFFFFFFF), (0x10, 4), (0x14, 0xFFFFFFFF), (0x14, 0)]
    for offset in (0x18, 0x1C, 0x20, 0x24):
        probe.extend(((offset, 0xFFFFFFFF), (offset, 0)))
    probe.extend(((0x30, 0xFFFFFFFE), (0x64, 0x8008)))
    return probe * 3 + [
        (0x10, base & 0xFFFFFFF0),
        (0x14, base >> 32),
        (4, 0x27),
        (4, 0),
        (4, 0),
        (0x3C, 0xFF),
        (4, 3),
        (4, 3),
        (4, 0),
        (4, 2),
        (4, 2),
        (0x3C, 0xB),
    ]


def validate_trace(trace, firmware, serial, mode, coverage, payload=None):
    measured = bar.validate(33 if mode in ("bar-read", "bar-prepare") else 35, serial, mode, payload)
    controls = validate_coverage(coverage)
    records, tx, tx_at, debug, debug_at = parse_trace(trace)
    need(normalized(tx) == normalized(serial), "Trace/serial byte stream mismatch (DLAB-aware)")
    need(normalized(debug) == normalized(firmware), "Trace/firmware byte stream mismatch")
    entry, _ = marker_index(tx, tx_at, "AURORA_UEFI_ENTRY")
    _, exited = marker_index(tx, tx_at, "AURORA_UEFI_EXIT_OK: attempts=1")
    _, pci_closed = marker_index(tx, tx_at, "AURORA_PCI_WINDOW_CLOSED: reads=39")
    need(entry < exited < pci_closed, "Trace serial phase order")
    resets = [r for r in records if r["name"] == "pci_nvme_pci_reset"]
    need(
        len(resets) == 1 and resets[0]["index"] < 8 and resets[0]["index"] < entry,
        "Missing initial reset or later controller reset",
    )
    need(
        not any(r["name"] == "pci_cfg_write" and r["index"] >= entry for r in records),
        "Aurora performed PCI config write",
    )
    target = [r for r in records if r["name"].startswith("pci_cfg_") and r["device"] == "nvme"]
    need(
        target and any(r["operation"] == "read" and r["offset"] == 0 and r["value"] == 0x101B36 for r in target),
        "Trace target identity missing",
    )
    final_commands = [
        r["value"] & 0xFFFF for r in target if r["operation"] == "read" and r["offset"] == 4 and r["index"] >= entry
    ]
    need(
        final_commands and all(v == measured["command"] for v in final_commands),
        "PCI command disagrees across trace/serial",
    )
    # A successful CPU exception probe must stop before its attempted transaction.
    reads = [r for r in records if r["name"] == "pci_nvme_mmio_read" and r["index"] >= entry]
    expected = list(bar.READS) if measured["reads"] else []
    need(
        [(r["address"], r["size"]) for r in reads] == expected,
        "Extra/missing/reordered/incorrect-width BAR transactions",
    )
    if reads:
        _, reconciled = marker_index(tx, tx_at, "AURORA_BAR_RESERVATIONS: count=3 matched=1")
        state_at, _ = marker_index(tx, tx_at, "AURORA_BAR_STATE:")
        need(all(reconciled < r["index"] < state_at for r in reads), "BAR read outside bounded diagnostic phase")
    need(
        not any(
            r["name"].startswith("pci_nvme_") and r["name"] != "pci_nvme_mmio_read" and r["index"] >= entry
            for r in records
        ),
        "Aurora initialized/wrote/signalled the NVMe controller",
    )
    clean = mode in bar.CLEAN
    if clean:
        need(
            all(
                r["name"] in ("pci_nvme_pci_reset", "pci_nvme_mmio_read")
                for r in records
                if r["name"].startswith("pci_nvme_")
            ),
            "Clean trace contains controller/queue/doorbell/DMA/interrupt event",
        )
        need(
            not any(r["name"] == "pci_nvme_mmio_read" and r["index"] < entry for r in records),
            "Firmware accessed NVMe registers",
        )
        markers = [line for line in normalized(firmware).splitlines() if "AURORA_FIXTURE" in line]
        need(markers == FIRMWARE_MARKERS, "Missing/malformed/contradictory clean firmware handoff markers")
        need("PhysBits: 40" in firmware, "Fixture physical width not established")
        marker_spans = []
        cursor = 0
        for marker in FIRMWARE_MARKERS:
            at = debug.find(marker, cursor)
            need(at >= 0, "Firmware marker absent from trace")
            marker_spans.append((debug_at[at], debug_at[at + len(marker) - 1]))
            cursor = at + len(marker)
        need(marker_spans[-1][1] < entry, "Firmware handoff ran after Aurora entry")
        command_writes = [r for r in target if r["operation"] == "write" and r["offset"] == 4]
        need(
            [r["value"] for r in command_writes] == [0, 0, 0, 0x27, 0, 0, 3, 3, 0, 2, 2],
            "Unbounded/foreign PCI command probe or final command",
        )
        need(
            marker_spans[0][1] < command_writes[-2]["index"] < marker_spans[1][0]
            and marker_spans[2][1] < command_writes[-1]["index"] < marker_spans[3][0],
            "Firmware command write/initial/final marker order disagrees",
        )
        begin, end = command_writes[3]["index"], command_writes[4]["index"]
        probe = [r for r in target if begin < r["index"] < end]
        need(
            [(r["operation"], r["offset"], r["value"]) for r in probe] == [("read", 4, 7)],
            "BME capability probe not immediately read back/restored",
        )
        need(end < entry and command_writes[-1]["index"] < entry, "Firmware command restoration too late")
        base, length = measured["base"], measured["length"]
        need(
            [(r["offset"], r["value"]) for r in target if r["operation"] == "write"] == expected_config_writes(base),
            "Target configuration writes differ from bounded observed enumeration",
        )
        bar_reads = [
            (r["offset"], r["value"])
            for r in target
            if r["operation"] == "read" and r["index"] >= entry and r["offset"] in (0x10, 0x14)
        ]
        need(
            bar_reads and all(v == ((base & 0xFFFFFFF0) | 4 if off == 0x10 else base >> 32) for off, v in bar_reads),
            "Trace BAR address disagrees with descriptor",
        )
    else:
        need("AURORA_FIXTURE" not in firmware, "Stock firmware unexpectedly claims clean fixture state")
        validate_stock_control(trace, require_state=mode == "bar-inherited")
    for r in records:
        if r["name"] == "msix_write_config":
            need(not clean and r["index"] < entry, "MSI-X enable/mask state changed")
        if r["name"] == "memory_region_ops_write" and (clean or r["index"] >= entry):
            need(
                r["region"] not in ("nvme", "msix-table", "msix-pba") and not r["region"].startswith("nvme-"),
                "NVMe or MSI-X memory write occurred",
            )
            if measured.get("base") is not None:
                need(
                    not (
                        r["address"] < measured["base"] + measured["length"]
                        and measured["base"] < r["address"] + r["size"]
                    ),
                    "Write overlapped NVMe BAR",
                )
    return dict(
        controls,
        reads=expected,
        command=measured["command"],
        transient_bme_probe=clean,
        dma_evidence="reset plus no initialization/queue/doorbell activity; not a universal DMA trace",
    )


def load_coverage(path):
    path = Path(path)
    result = json.loads(path.read_text())
    for key in ("events", "available_events", "stock_trace"):
        result[key] = (path.parent / result[key]).read_text()
    result["msix_control"] = str(path.parent / result["msix_control"])
    return result


def fixture_control():
    """Synthetic parser input only; independent real controls remain mandatory."""
    protocol = [
        {"kind": "qmp-greeting", "data": {"QMP": {"version": {"qemu": {"major": 10, "minor": 0, "micro": 13}}}}}
    ]
    native = ["[I 0] OPENED"]
    trace = [RESET]

    def qmp(operation, value, arguments=None):
        request = {"execute": operation}
        if arguments is not None:
            request["arguments"] = arguments
        protocol.extend(({"kind": "qmp-request", "data": request}, {"kind": "qmp-response", "data": {"return": value}}))

    def qt(request, response="OK"):
        protocol.extend(({"kind": "qtest-request", "data": request}, {"kind": "qtest-response", "data": response}))
        native.extend(("[R +0] " + request, "[S +0] " + response))

    def read_config(offset, value):
        qt(f"outl 0xcf8 0x{0x80001000 + (offset & ~3):x}")
        qt(f"inw 0x{0xCFC + (offset & 3):x}", f"OK 0x{value:x}")
        trace.append(f"pci_cfg_read nvme 00:02.0 @0x{offset:x} -> 0x{value:x}")

    def write_config(offset, value):
        qt(f"outl 0xcf8 0x{0x80001000 + offset:x}")
        qt(f"outl 0xcfc 0x{value:x}")
        trace.append(f"pci_cfg_write nvme 00:02.0 @0x{offset:x} <- 0x{value:x}")

    def mmio_state():
        for offset in (0x14, 0x1C, 0x24, 0x28, 0x2C, 0x30, 0x34):
            qt(f"readl 0x{0xC0000000 + offset:x}", "OK 0x0")
            trace.append(f"pci_nvme_mmio_read addr 0x{offset:x} size 4")

    pci = [{"bus": 0, "devices": [{"id": {"vendor": 0x1B36, "device": 0x10}, "slot": 2, "function": 0}]}]
    qmp("qmp_capabilities", {})
    qmp("query-status", {"running": False, "status": "prelaunch"})
    qmp("query-block", [])
    qmp("query-pci", pci)
    qmp("human-monitor-command", "synthetic qtree", {"command-line": "info qtree"})
    for offset, value in (
        (0, 0x101B36),
        (8, 0x1080202),
        (0xE, 0),
        (4, 0),
        (0x10, 4),
        (0x14, 0),
        (0x34, 0x40),
        (0x40, 0x11),
        (0x42, 0x40),
        (0x44, 0x2000),
    ):
        read_config(offset, value)
    write_config(0x10, 0xC0000004)
    write_config(0x14, 0)
    write_config(4, 2)
    read_config(4, 2)
    read_config(0x42, 0x40)
    mmio_state()
    qt("readl 0xc000200c", "OK 0x1")
    qt("writel 0xc000200c 0x1")
    trace.append("memory_region_ops_write cpu -1 mr 0x1 addr 0xc000200c value 0x1 size 4 name 'msix-table'")
    qt("readl 0xc000200c", "OK 0x1")
    mmio_state()
    read_config(4, 2)
    read_config(0x42, 0x40)
    qmp("query-status", {"running": False, "status": "prelaunch"})
    native.append("[I +0] CLOSED")
    artifacts = {
        "invocation.json": json.dumps({"argv": ["qemu", "-S", "-nodefaults", "-device", "nvme,bus=pcie.0,addr=02.0"]}),
        "protocol.jsonl": "\n".join(map(json.dumps, protocol)) + "\n",
        "trace.log": "\n".join(trace) + "\n",
        "result.json": json.dumps(
            {
                "control_passed": True,
                "cpu_running": False,
                "namespace_backends": [],
                "bdf": "0000:00:02.0",
                "vendor_device": "1b36:0010",
            }
        ),
        "qtest-native.log": "\n".join(native) + "\n",
        "query-pci.json": json.dumps(pci),
        "qtree.txt": "synthetic qtree",
        "stderr.log": "",
        "trace-verification.json": "{}",
        "control.py": "# Synthetic parser fixture",
        "verify-trace.py": "# Synthetic parser fixture",
    }
    return resign_control(artifacts)


def resign_control(artifacts):
    result = dict(artifacts)
    result["SHA256SUMS"] = "".join(
        hashlib.sha256(data.encode()).hexdigest() + "  " + name + "\n"
        for name, data in sorted(result.items())
        if name != "SHA256SUMS"
    )
    return result


def self_test():
    # Controls are validated independently below; synthetic trace cases exercise
    # the complete receipt parser with a locally replaced coverage checker only.
    # Production validate_trace always calls the real coverage checker.
    global validate_coverage
    actual_coverage = validate_coverage
    validate_coverage = lambda value: {} if value == {"self_test": True} else actual_coverage(value)
    failures = 0

    def write(address, value, region="serial"):
        return f"memory_region_ops_write cpu 0 mr 0x1 addr 0x{address:x} value 0x{value:x} size 1 name '{region}'\n"

    def emit(text, region="serial"):
        return "".join(write(0x402 if region == "isa-debugcon" else 0x3F8, ord(c), region) for c in text)

    firmware = "PhysBits: 40\n" + "\n".join(FIRMWARE_MARKERS) + "\n"
    for mode in bar.CLEAN:
        status, serial, payload = bar.fixture(mode)
        pre = RESET + "\n" + emit("PhysBits: 40\n", "isa-debugcon")
        marker = 0
        for offset, value in expected_config_writes(0xC000000000):
            if offset == 4 and value == 2:
                pre += emit(FIRMWARE_MARKERS[marker] + "\n", "isa-debugcon")
            pre += f"pci_cfg_write nvme 00:02.0 @0x{offset:x} <- 0x{value:x}\n"
            if offset == 4 and value == 0x27:
                pre += "pci_cfg_read nvme 00:02.0 @0x4 -> 0x7\n"
            if offset == 4 and value == 2:
                pre += emit(FIRMWARE_MARKERS[marker + 1] + "\n", "isa-debugcon")
                marker += 2
        pre += "pci_cfg_read nvme 00:02.0 @0x0 -> 0x101b36\n"
        # Non-output divisor write is deliberately non-ASCII.
        pre += write(0x3FB, 0x80) + write(0x3F8, 0xFF) + write(0x3FB, 3)
        trace = pre
        for line in serial.splitlines(True):
            trace += emit(line)
            if line == "AURORA_UEFI_ENTRY\n":
                trace += (
                    "pci_cfg_read nvme 00:02.0 @0x4 -> 0x100002\npci_cfg_read nvme 00:02.0 @0x10 -> 0x4\npci_cf"
                    "g_read nvme 00:02.0 @0x14 -> 0xc0\n"
                )
            if line == "AURORA_BAR_RESERVATIONS: count=3 matched=1\n" and mode != "bar-alias":
                trace += "".join(f"pci_nvme_mmio_read addr 0x{o:x} size {w}\n" for o, w in bar.READS)
        validate_trace(trace, firmware, serial, mode, {"self_test": True}, payload)
        bad = [
            trace.rstrip("\n"),
            trace.replace(RESET + "\n", ""),
            trace + RESET + "\n",
            trace + "pci_cfg_write nvme 00:02.0 @0x4 <- 0x2\n",
            trace.replace(" <- 0x27\n", " <- 0x7\n", 1),
            trace.replace(" -> 0x7\n", " -> 0x3\n", 1),
            trace.replace("size 1 name", "size 3 name", 1),
            trace.replace("nvme 00:02.0", "nvme 00:03.0", 1),
            trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xc00000200c value 0x1 size 4 name 'msix-table'\n",
            trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xc000000008 value 0x0 size 4 name 'foreign'\n",
            trace + "msix_write_config dev nvme enabled 0 masked 1\n",
            trace + "pci_nvme_mmio_read addr 0x8 size 4\n",
            trace + "unknown_trace write\n",
            trace.replace(RESET + "\n", RESET + "\npci_cfg_write nvme 00:02.0 @0x3 <- 0x400\n", 1),
            trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xbfffffffff value 0x0 size 4 name 'foreign'\n",
            trace + "memory_region_ops_write cpu 0 mr 0x1 addr 0xffffffffffffffff value 0x0 size 4 name 'foreign'\n",
        ]
        for event in sorted(EVENTS):
            if event.startswith("pci_nvme_") and event not in ("pci_nvme_pci_reset", "pci_nvme_mmio_read"):
                bad.append(trace + event + " injected\n")
        for line in [r for r in trace.splitlines(True) if r.startswith("pci_nvme_mmio_read")]:
            bad.extend(
                (
                    trace.replace(line, "", 1),
                    trace.replace(line, line * 2, 1),
                    trace.replace(
                        line,
                        line.replace("size 8", "size 4") if "size 8" in line else line.replace("size 4", "size 8"),
                        1,
                    ),
                )
            )
        for candidate in bad:
            try:
                validate_trace(candidate, firmware, serial, mode, {"self_test": True}, payload)
            except ValueError:
                failures += 1
            else:
                raise RuntimeError("Invalid synthetic BAR trace accepted: " + mode)
        for extra in ("AURORA_FIXTURE_FAIL: initial command read/BME\n", "AURORA_FIXTURE_UNKNOWN: ignored\n"):
            try:
                validate_trace(
                    trace + emit(extra, "isa-debugcon"), firmware + extra, serial, mode, {"self_test": True}, payload
                )
            except ValueError:
                failures += 1
            else:
                raise RuntimeError("Firmware failure/unknown record accepted")
        moved = "".join(line for line in trace.splitlines(True) if "name 'isa-debugcon'" not in line) + emit(
            firmware, "isa-debugcon"
        )
        try:
            validate_trace(moved, firmware, serial, mode, {"self_test": True}, payload)
        except ValueError:
            failures += 1
        else:
            raise RuntimeError("Post-Aurora firmware handoff accepted")
        for malformed in ("", "AURORA_FIXTURE_NVME: malformed\n", firmware.replace("0x0000", "0x0007", 1)):
            try:
                validate_trace(trace, malformed, serial, mode, {"self_test": True}, payload)
            except ValueError:
                failures += 1
            else:
                raise RuntimeError("Mismatched firmware accepted")
    for mode in ("bar-state", "bar-capture", "bar-inherited"):
        _, serial, payload = bar.fixture(mode)
        trace = RESET + "\n" + "pci_cfg_read nvme 00:02.0 @0x0 -> 0x101b36\n"
        for event in (
            "pci_nvme_mmio_cfg",
            "pci_nvme_mmio_aqattr",
            "pci_nvme_mmio_asqaddr",
            "pci_nvme_mmio_acqaddr",
            "pci_nvme_mmio_start_success",
            "pci_nvme_mmio_doorbell_sq",
            "pci_nvme_mmio_doorbell_cq",
            "pci_nvme_create_sq",
            "pci_nvme_create_cq",
            "pci_nvme_irq_pin",
        ):
            trace += event + " synthetic initialization\n"
        trace += "memory_region_ops_write cpu 0 mr 0x1 addr 0xc000000014 value 0x460001 size 4 name 'nvme'\n"
        for line in serial.splitlines(True):
            trace += emit(line)
            if line == "AURORA_UEFI_ENTRY\n":
                trace += "pci_cfg_read nvme 00:02.0 @0x4 -> 0x100007\n"
            if line == "AURORA_BAR_RESERVATIONS: count=3 matched=1\n":
                trace += "".join(f"pci_nvme_mmio_read addr 0x{o:x} size {w}\n" for o, w in bar.READS)
        validate_trace(trace, "", serial, mode, {"self_test": True}, payload)
        for extra in (
            "pci_nvme_mmio_read addr 0x8 size 4\n",
            "pci_nvme_irq_pin unexpected\n",
            "pci_cfg_write nvme 00:02.0 @0x4 <- 0x7\n",
        ):
            try:
                validate_trace(trace + extra, "", serial, mode, {"self_test": True}, payload)
            except ValueError:
                failures += 1
            else:
                raise RuntimeError("Stock-mode post-entry activity accepted")
    validate_coverage = actual_coverage
    control = fixture_control()
    verify_msix_control(control)
    mutations = []
    for name in control:
        changed = dict(control)
        changed.pop(name)
        mutations.append(changed)
        if name != "SHA256SUMS":
            changed = dict(control)
            changed[name] += "corrupt"
            mutations.append(changed)
    for name, old, new in (
        ("invocation.json", '"-S"', '"-no-shutdown"'),
        ("protocol.jsonl", '"running": false', '"running": true'),
        ("trace.log", "value 0x1 size 4", "value 0x0 size 4"),
        ("trace.log", "pci_nvme_mmio_read addr 0x14 size 4", "pci_nvme_mmio_read addr 0x18 size 4"),
        ("qtest-native.log", "writel 0xc000200c 0x1", "writel 0xc000200c 0x0"),
        ("result.json", '"cpu_running": false', '"cpu_running": true'),
    ):
        changed = dict(control)
        changed[name] = changed[name].replace(old, new, 1)
        mutations.append(resign_control(changed))
    for candidate in mutations:
        try:
            verify_msix_control(candidate)
        except (ValueError, KeyError):
            failures += 1
        else:
            raise RuntimeError("Malformed MSI-X coverage control accepted")
    for coverage in (
        {},
        {"qemu_version": "10.0.12"},
        {"qemu_version": "10.0.13", "events": EVENT_TEXT[:-1]},
        {"qemu_version": "10.0.13", "events": EVENT_TEXT, "available_events": EVENT_TEXT},
    ):
        try:
            validate_coverage(coverage)
        except (ValueError, KeyError):
            failures += 1
        else:
            raise RuntimeError("Incomplete coverage accepted")
    print(
        f"PASS: BAR trace {len(bar.MODES)} synthetic positive and {failures}"
        f" adversarial cases; real controls required separately"
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
    else:
        try:
            result = validate_trace(
                Path(sys.argv[1]).read_text(),
                Path(sys.argv[2]).read_text(),
                Path(sys.argv[3]).read_text(),
                sys.argv[4],
                load_coverage(sys.argv[5]),
                json.loads(Path(sys.argv[6]).read_text()) if len(sys.argv) > 6 else None,
            )
        except (ValueError, KeyError, IndexError, OSError) as error:
            sys.exit("FAIL: " + str(error))
        print("PASS: strict BAR hardware trace " + json.dumps(result, sort_keys=True))
