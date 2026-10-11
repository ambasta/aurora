# Host-only bridges assembled with their matching generated Aurora roots.
# Private source entries remain local; only these test adapters are exported.
.text
.ifdef NOTE_TEST_INITIAL
.global note_test_initial
.type note_test_initial,@function
note_test_initial:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call __au_v_m1_20program_note_initial_n0__d12initial_note
    leave
    ret
.size note_test_initial,.-note_test_initial
.global files_test_initial
.type files_test_initial,@function
files_test_initial:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call __au_v_m1_20program_note_initial_n0__d13initial_files
    leave
    ret
.size files_test_initial,.-files_test_initial
.else
.global note_test_service
.type note_test_service,@function
note_test_service:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r11
    call __au_v_m1_22program_stream_service_n0__d16aurora_user_main
    leave
    ret
.size note_test_service,.-note_test_service
.endif
