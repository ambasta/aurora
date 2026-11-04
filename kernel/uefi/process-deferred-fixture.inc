// Case 107 explicitly abandons one undispatched call; it is not natural service death.
// Clients in case 102 run sequentially, exercising slot reuse rather than concurrency.
// Included only by the existing process fixture, after dispatch_deferred.
// Real client traps and the production receipt dispatcher own every transition.
constexpr std::string_view deferred_fixture_expected{"1 file not_found 0 #0 \ndeferred-ok2 print success \n"};
constinit U64 deferred_fixture_output_bytes = 0;
auto deferred_fixture_output(void *, bool error, std::span<const std::byte> bytes) -> bool {
    if (error || deferred_fixture_output_bytes + bytes.size() > deferred_fixture_expected.size())
        fail("deferred fixture output bounds");
    for (const auto byte : bytes)
        if (byte != std::byte(static_cast<unsigned char>(deferred_fixture_expected[deferred_fixture_output_bytes++])))
            fail("deferred fixture output bytes");
    return true;
}
auto deferred_fixture_marker(U64 kind, std::string_view stage) -> void {
    Serial::text("AURORA_DEFERRED_PROBE:");
    field("case", deferred_probe_case);
    field("kind", kind);
    Serial::text(" stage=");
    Serial::text(stage);
    Serial::text("\r\n");
}
auto run_deferred_fixture_client(U64 service_baseline) -> bool {
    const U64 client = residents[1].state.run;
    U64 requests = 0, outputs = 0;
    deferred_fixture_output_bytes = 0;
    deferred_fixture_scope = true;
    while (residents[1].space) {
        if (run_resident(1))
            break;
        const U64 kind = outcome.request ? 1 : outcome.output ? 2 : 0;
        if (!kind)
            continue;
        if (deferred_calls[0].kind != kind || endpoint.caller ||
            endpoint_owner.observe().phase != aurora::endpoint::Phase::waiting)
            fail("deferred fixture captured boundary");
        if (kind == 1 && !requests) {
            deferred_fixture_marker(kind, "captured");
            if (deferred_probe_case == 103)
                deferred_calls[0].frame[0] ^= 1; // Non-argument GPR, not just decoded operands.
            if (deferred_probe_case == 104)
                deferred_calls[0].root ^= frames::page;
            if (deferred_probe_case == 105)
                ++deferred_calls[0].generation;
            if (deferred_probe_case == 107) {
                abandon_service();
                if (residents[0].space || clients_live() || deferred_calls[0].kind || deferred_calls[1].kind ||
                    endpoint.generation || table.free() != service_baseline || !audit_residents())
                    fail("deferred fixture abandonment cleanup");
                deferred_fixture_marker(kind, "abandoned-reclaimed");
                dispatch_deferred(1, kind);
                fail("deferred fixture stale dispatch returned");
            }
        }
        dispatch_deferred(1, kind);
        if (deferred_calls[0].kind)
            fail("deferred fixture receipt not consumed");
        if (kind == 1) {
            if (!client_request() || endpoint.caller_cancelled || !execution_owner.complete(1))
                fail("deferred fixture actual reply");
            ++requests;
            if (endpoint.caller || endpoint_owner.observe().phase != aurora::endpoint::Phase::waiting ||
                endpoint_owner.observe().completion())
                fail("deferred fixture reply not settled");
            if (deferred_probe_case == 106) {
                deferred_fixture_marker(kind, "completed-endpoint-free");
                dispatch_deferred(1, kind);
                fail("deferred fixture replay returned");
            }
        } else {
            if (!deliver_output())
                fail("deferred fixture actual output");
            ++outputs;
        }
    }
    if (!outcome.exited || outcome.status || requests != 1 || !outputs ||
        deferred_fixture_output_bytes != deferred_fixture_expected.size() || deferred_calls[0].kind ||
        !audit_residents())
        fail("deferred fixture client result");
    endpoint.caller.reset();
    if (!endpoint_owner.finish_client(client))
        fail("deferred fixture client finalization");
    deferred_fixture_scope = false;
    Serial::text("AURORA_DEFERRED_CLIENT_OK:");
    field("client", client);
    field("requests", requests);
    field("outputs", outputs);
    field("bytes", deferred_fixture_output_bytes);
    Serial::text(" exact=1 retired=1\r\n");
    return true;
}
