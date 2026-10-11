#!/usr/bin/env python3
"""Run only in-memory host tests; prints model counts, never accesses devices."""

import copy
import unittest

from durability import (
    Corruption,
    Conflict,
    OutcomeExpired,
    Pressure,
    OLD,
    NEW,
    FS,
    EPOCH,
    SEQUENCE,
    seal,
    decode,
    digest,
    transaction,
    recover,
    verify_protocol,
    OutcomeWindow,
)


def rewrite_manifest(records, body):
    records["manifest"] = seal(2, body)
    commit = decode(records["commit"], 3)
    commit["digest"] = digest(records["manifest"])
    records["commit"] = seal(3, commit)


class DurabilityTests(unittest.TestCase):
    def test_safe_protocol_all_crash_images(self):
        result = verify_protocol()
        self.assertEqual(result["violations"], [])
        self.assertGreater(result["crash_images"], 100)
        self.assertGreater(result["unacknowledged_new_states"], 0)

    def test_single_final_flush_is_detected_as_broken(self):
        result = verify_protocol(dependency_fence=False)
        self.assertTrue(result["violations"])
        self.assertTrue(
            any(
                v["cut"] == "submit-commit" and v["masks"]["commit"] == 3 and v["masks"]["manifest"] != 3
                for v in result["violations"]
            )
        )

    def test_missing_commit_durability_fence_loses_acknowledgement(self):
        result = verify_protocol(commit_fence=False)
        self.assertTrue(
            any(v["cut"] == "acknowledge" and v["reason"] == "acknowledged commit lost" for v in result["violations"])
        )

    def test_unacknowledged_valid_commit_is_recovered(self):
        state, receipt = recover(transaction())
        self.assertEqual(state, NEW)
        self.assertEqual(receipt, (1, digest(b"replace a and b"), SEQUENCE))

    def test_no_commit_leaves_old_state(self):
        records = transaction()
        del records["commit"]
        self.assertEqual(recover(records), (OLD, None))

    def test_dependency_loss_is_corruption_not_silent_rollback(self):
        for slot in ("data-a", "data-b", "manifest"):
            with self.subTest(slot=slot):
                records = transaction()
                del records[slot]
                with self.assertRaises(Corruption):
                    recover(records)
                self.assertEqual(OLD, {"a": "old-a", "b": "old-b"})

    def test_every_record_byte_bit_flip_and_truncation(self):
        for slot, raw in transaction().items():
            kind = 3 if slot == "commit" else 2 if slot == "manifest" else 1
            for index in range(len(raw)):
                altered = raw[:index] + bytes((raw[index] ^ 1,)) + raw[index + 1 :]
                self.assertIsNone(decode(altered, kind), (slot, index))
                self.assertIsNone(decode(raw[:index], kind), (slot, index))
            self.assertIsNone(decode(raw + b"x", kind))

    def test_valid_checksums_do_not_override_identity(self):
        for field, value in (("fs", "another-volume"), ("epoch", EPOCH + 1), ("object", "b"), ("generation", 7)):
            with self.subTest(field=field):
                records = transaction()
                data = decode(records["data-a"], 1)
                data[field] = value
                records["data-a"] = seal(1, data)
                manifest = decode(records["manifest"], 2)
                manifest["refs"][0]["digest"] = digest(records["data-a"])
                rewrite_manifest(records, manifest)
                with self.assertRaises(Corruption):
                    recover(records)

    def test_valid_checksums_do_not_override_manifest_or_commit_contract(self):
        fields = (
            ("previous", 8),
            ("sequence", SEQUENCE + 1),
            ("fs", "other"),
            ("epoch", 5),
            ("request", True),
            ("request_digest", "other"),
        )
        for field, value in fields:
            records = transaction()
            manifest = decode(records["manifest"], 2)
            manifest[field] = value
            rewrite_manifest(records, manifest)
            with self.subTest(field=field), self.assertRaises(Corruption):
                recover(records)
        for field, value in (("fs", "other"), ("epoch", 7), ("sequence", SEQUENCE - 1), ("manifest", "elsewhere")):
            records = transaction()
            body = decode(records["commit"], 3)
            body[field] = value
            records["commit"] = seal(3, body)
            with self.subTest(field=field), self.assertRaises(Corruption):
                recover(records)

    def test_malformed_and_duplicate_reference_shapes(self):
        base = decode(transaction()["manifest"], 2)
        for refs in (
            None,
            {},
            [],
            base["refs"][:1],
            base["refs"] * 4,
            [base["refs"][0], base["refs"][0]],
            [[], []],
            [{"slot": [], "object": [], "generation": 8, "digest": "x"}] * 2,
        ):
            records = transaction()
            body = copy.deepcopy(base)
            body["refs"] = refs
            rewrite_manifest(records, body)
            with self.subTest(refs=refs), self.assertRaises(Corruption):
                recover(records)

    def test_lost_reply_retry_returns_same_durable_result(self):
        state, receipt = recover(transaction())
        window = OutcomeWindow(2)
        request, request_digest, result = receipt
        window.record(request, request_digest, result)
        self.assertEqual(window.query(request, request_digest), result)
        self.assertEqual(window.record(request, request_digest, result), result)
        self.assertEqual(len(window.entries), 1)
        with self.assertRaises(Conflict):
            window.query(request, "different-write")
        with self.assertRaises(Conflict):
            window.record(request, request_digest, result + 1)

    def test_bounded_outcome_retention_does_not_reexecute_expired_token(self):
        window = OutcomeWindow(2)
        window.record(1, "digest-1", 11)
        window.record(2, "digest-2", 12)
        with self.assertRaises(Pressure):
            window.record(3, "digest-3", 13)
        window.expire_through(1)
        window.record(3, "digest-3", 13)
        self.assertEqual(len(window.entries), 2)
        with self.assertRaises(OutcomeExpired):
            window.query(1, "digest-1")
        with self.assertRaises(OutcomeExpired):
            window.record(1, "digest-1", 14)
        self.assertIsNone(window.query(4, "digest-4"))

    def test_null_outcome_cannot_erase_first_wins_contract(self):
        # Parent review regression: None previously looked like an absent entry,
        # allowing a later retry to overwrite it with a different terminal result.
        window = OutcomeWindow(2)
        for outcome in (None, True, False, 0, -1, 1.0, "11", [], 1 << 64):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                window.record(1, "same-digest", outcome)
            self.assertEqual(window.entries, {})
        window.record(1, "same-digest", 99)
        with self.assertRaises(Conflict):
            window.record(1, "same-digest", 100)
        self.assertEqual(window.query(1, "same-digest"), 99)

    def test_outcome_window_explicit_type_and_range_bounds(self):
        for capacity in (None, True, 2.0, 0, -1, 65, "2"):
            with self.subTest(capacity=capacity), self.assertRaises(ValueError):
                OutcomeWindow(capacity)
        window = OutcomeWindow(2)
        for request in (None, True, 1.0, 0, -1, 1 << 64):
            with self.subTest(request=request), self.assertRaises(ValueError):
                window.record(request, "digest", 11)
        for request_digest in (None, "", [], "a" * 129):
            with self.subTest(digest=request_digest), self.assertRaises(ValueError):
                window.record(1, request_digest, 11)
        self.assertEqual(window.entries, {})
        for expiry in (None, True, 1.0, -1, 1 << 64):
            with self.subTest(expiry=expiry), self.assertRaises(ValueError):
                window.expire_through(expiry)


if __name__ == "__main__":
    print("HOST-ONLY durability model; no disk/driver/target filesystem coverage", flush=True)
    for label, options in (
        ("safe two-fence", {}),
        ("broken single-final-flush", {"dependency_fence": False}),
        ("broken premature-ack", {"commit_fence": False}),
    ):
        result = verify_protocol(**options)
        print(
            f"{label}: {result['crash_images']} crash images; "
            f"{len(result['violations'])} violations; "
            f"{result['unacknowledged_new_states']} valid unacknowledged new states",
            flush=True,
        )
        if result["violations"]:
            print("  first counterexample:", result["violations"][0], flush=True)
    unittest.main(verbosity=2)
