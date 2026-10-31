# WORD_VIEW_TEST_ABI: test-only fixed word owner; no native span parameters or results.
.text
.global __au_runtime_word_view_construct
.hidden __au_runtime_word_view_construct
.type __au_runtime_word_view_construct,@function
__au_runtime_word_view_construct:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%r11
    call @kernel_word_test::WordViewFixture@
    leave
    ret
.size __au_runtime_word_view_construct,.-__au_runtime_word_view_construct
.global __au_runtime_word_view_read
.hidden __au_runtime_word_view_read
.type __au_runtime_word_view_read,@function
__au_runtime_word_view_read:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    movq %rsi,%rdi
    call @process_word_view_read@
    leave
    ret
.size __au_runtime_word_view_read,.-__au_runtime_word_view_read
.global __au_runtime_word_view_finish
.hidden __au_runtime_word_view_finish
.type __au_runtime_word_view_finish,@function
__au_runtime_word_view_finish:
    pushq %rbp
    movq %rsp,%rbp
    movq %rdi,%r10
    call @kernel_word_test::finish@
    leave
    ret
.size __au_runtime_word_view_finish,.-__au_runtime_word_view_finish
