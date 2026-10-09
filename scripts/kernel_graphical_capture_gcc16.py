"""Closed GCC16 capture emission proof, using original linked instructions.

The caller supplies the existing checker/decoder and independently verifies the
complete source/tool tuple, object relocations and .ci/.su bindings. This module
never normalizes an instruction or imports the parent checker. Its exact emitted
inventory is an explicit qualification boundary, not a general compiler proof.
"""

import hashlib

FILES = {
    "graphical-console.ci": "87cef425b613779efb6a8621c0c8ff9dcccba9d8a51a77f2755afe0542fda188",
    "graphical-console.o": "3208d43fb6660953432e8f6d108837a387322314394a8cb7a14dcc6aa8ef54c8",
    "graphical-console.su": "7015fb5d36064a2915971b3c1159d2aca49ef7ecd53348270871916ab1b300eb",
    "language.o": "ecab8fa007f5f9b2320c7e088631b2f376eda9e50b15aaa2618e29641ad219c2",
    "language.s": "e554e294ee0d9c91542b70c79c2907974ae69ee27f4076f562e7b3bbfb279c5d",
    "payload.bin": "01ec248de06cd591ed5032e8face0125897d943918e7d69e7440e5dfe1ffacfb",
    "payload.elf": "b47d96471f9480b89f44010b1af1d41918e5c4577700ac31220cf7216f521d19",
}

BODIES = {
    "_ZN6aurora4uefi12_GLOBAL__N_115ServicePlatform4failEv": (
        19024,
        21,
        4,
        "ccdfb7b6d0c094890c855ff2d8c6a36396d82277804a99e55ca153521e12dc39",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_1L13timer_mappingEv": (
        15936,
        165,
        40,
        "72caf9840ee667839a7fe9449f4d6ed6e7ff822da26552f880aee27b0f9b2a79",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_1L15wait_for_sampleEv": (
        19632,
        615,
        127,
        "65fedafb90c4f61d6eb0993840de77e0313dee9e0d3d6075d6268d2afcdad617",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE": (
        16352,
        2666,
        673,
        "61631c173e295762dde44c97234edda30a50c60e09e1487f9cfc7baa997fef47",
    ),
    "_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv": (
        16112,
        238,
        69,
        "01ced15edd52d725a8820a9b5acb636eb94ea839112802cc9c67441d99a74f12",
    ),
    "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE": (
        23552,
        8448,
        1908,
        "1f00ebaf084ff589fb36319cc6da89d96ec311abc0667bdd1b77ae4660c6543b",
    ),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE4openEv": (
        19152,
        105,
        23,
        "e459dc30b7f1a762cee40d48bb6fe103bdaedf552b0d2afd601524ff585a0c27",
    ),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb": (
        19056,
        81,
        23,
        "b52c563c2d3e34489e29ca55c8d887a456ce60eea2c14bea283c50bf232d8dd5",
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE4openEv": (
        19392,
        228,
        47,
        "bbf2d5750db1c8df706eecd1c4ba5191df29bcda8c84cf3e72da5cf66ac1b562",
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb": (
        19264,
        126,
        35,
        "1be7b7be1314997f7b9b67551335596466d5e622a6d33edb8a2c43d70d677f0a",
    ),
    "_ZN6aurora8hardware6Serial4textESt17basic_string_viewIcSt11char_traitsIcEE": (
        7024,
        66,
        21,
        "ea34b996bdaa1b7fa411880bc45e56922c765846cf91272d77154e1ab81d912d",
    ),
    "_ZN6aurora8hardware6Serial6numberEy": (
        7104,
        198,
        48,
        "e06bc5eebe08ca71762185b3fe6ec85fc043b546dc7ad4ada6ed85287c782106",
    ),
    "__au_runtime_console_next": (20256, 1268, 315, "beed8e0ed696cbafca1a203ceaecd14ec3525f81b8f68355371d90ff93534aa4"),
    "__au_runtime_console_put": (21536, 253, 68, "4d4c9bc6c81219ecc99519c0ef252dab7e586c7230b8f8d192d9c6184878aad2"),
    "__au_runtime_display_pixel": (21792, 919, 189, "e9917df33796367d797aa4904a6203cb2cf8432b53548884b26e2d07511f054c"),
}

STATE = {
    "_ZN6aurora4uefi12_GLOBAL__N_1L10wait_stackE": (74264, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L11kernel_rootE": (74272, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L11owned_arenaE": (74280, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L11table_countE": (74240, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L12sample_callsE": (74208, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L13expected_wakeE": (74248, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L14pixel_attemptsE": (74176, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L15output_attemptsE": (74200, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L16active_operationE": (74224, 4, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L16capture_scenarioE": (74184, 1, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L16consumer_entriesE": (74216, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L17completed_samplesE": (74192, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L5readyE": (74105, 1, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L5wakesE": (74256, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L6storesE": (74232, 8, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L7waitingE": (74104, 1, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L8graphicsE": (74112, 64, 3, 1),
    "_ZN6aurora4uefi12_GLOBAL__N_1L9admissionE": (74080, 24, 3, 1),
    "_ZN6aurora7console4UartINS_8hardware2IoELNS0_11FifoTriggerE192EE14receive_error_E": (74288, 1, 3, 1),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE11generation_E": (
        74032,
        8,
        3,
        1,
    ),
    "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE6grant_E": (
        74048,
        24,
        3,
        1,
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE11generation_E": (
        73960,
        8,
        3,
        1,
    ),
    "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE6grant_E": (
        73984,
        48,
        3,
        1,
    ),
    (
        "_ZN6aurora9graphical5EntryINS_7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransport"
        "ENS5_15ServicePlatformEEENS_7display7SessionINS5_16DisplayTransportES7_EES7_E7active_E"
    ): (
        73952,
        1,
        3,
        1,
    ),
}

RUN = "_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE"
CONSOLE = "_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE"
DISPLAY = "_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE"
FAIL = "_ZN6aurora4uefi12_GLOBAL__N_1L4failESt17basic_string_viewIcSt11char_traitsIcEE"
PIXEL = "__au_runtime_display_pixel"

AUTHORITY_OPERATIONS = {
    19056: ("lea", "0xd6c9(%rip),%rax"),
    19063: ("sub", "$0x8,%rsp"),
    19067: ("cmp", "%rax,%rdi"),
    19070: (
        "jne",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19072: ("movabs", "$0x415552434f4e5301,%rax"),
    19082: ("cmp", "%rax,(%rdi)"),
    19085: (
        "jne",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19087: ("cmpb", "$0x0,0x10(%rdi)"),
    19091: (
        "je",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19093: ("cmp", "%dl,0x11(%rdi)"),
    19096: (
        "jne",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19098: ("test", "%rsi,%rsi"),
    19101: (
        "je",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19103: ("cmp", "%rsi,0xd68a(%rip)"),
    19110: (
        "jne",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19112: ("cmp", "%rsi,0x8(%rdi)"),
    19116: (
        "jne",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19118: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    19123: ("test", "%al,%al"),
    19125: (
        "je",
        "4abc "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE8validateEPKvmb+0x4c>",
    ),
    19127: ("add", "$0x8,%rsp"),
    19131: ("ret", ""),
    19132: ("call", "4a50 <_ZN6aurora4uefi12_GLOBAL__N_115ServicePlatform4failEv>"),
    19264: ("lea", "0xd5b9(%rip),%rax"),
    19271: ("push", "%rbx"),
    19272: ("cmp", "%rax,%rdi"),
    19275: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19277: ("movabs", "$0x4155524449535001,%rax"),
    19287: ("mov", "%rdi,%rbx"),
    19290: ("cmp", "%rax,(%rdi)"),
    19293: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19295: ("cmpb", "$0x0,0x28(%rdi)"),
    19299: (
        "je",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19301: ("cmp", "%dl,0x29(%rdi)"),
    19304: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19306: ("test", "%rsi,%rsi"),
    19309: (
        "je",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19311: ("cmp", "%rsi,0xd572(%rip)"),
    19318: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19320: ("cmp", "%rsi,0x8(%rdi)"),
    19324: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19326: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    19331: ("test", "%al,%al"),
    19333: (
        "je",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19335: ("mov", "0x10(%rbx),%rax"),
    19339: ("test", "%rax,%rax"),
    19342: (
        "je",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19344: ("cmp", "0xd689(%rip),%rax"),
    19351: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19353: ("mov", "0xd601(%rip),%eax"),
    19359: ("cmp", "%rax,0xd572(%rip)"),
    19366: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19368: ("mov", "0xd5f6(%rip),%eax"),
    19374: ("cmp", "%rax,0xd56b(%rip)"),
    19381: (
        "jne",
        "4bb9 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb+0x79>",
    ),
    19383: ("pop", "%rbx"),
    19384: ("ret", ""),
    19385: ("call", "4a50 <_ZN6aurora4uefi12_GLOBAL__N_115ServicePlatform4failEv>"),
    19153: ("mov", "0xd658(%rip),%rbx"),
    19160: ("cmp", "$0xffffffffffffffff,%rbx"),
    19164: (
        "je",
        "4b34 "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE4openEv+0x64>",
    ),
    19166: ("cmpb", "$0x0,0xd66b(%rip)"),
    19173: (
        "jne",
        "4b34 "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE4openEv+0x64>",
    ),
    19175: ("cmpb", "$0x0,0xd663(%rip)"),
    19182: (
        "jne",
        "4b34 "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE4openEv+0x64>",
    ),
    19184: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    19189: ("test", "%al,%al"),
    19191: (
        "je",
        "4b34 "
        "<_ZN6aurora7console7SessionINS_4uefi12_GLOBAL__N_116ServiceTransportENS3_15ServicePlatformEE4openEv+0x64>",
    ),
    19193: ("movabs", "$0x415552434f4e5301,%rax"),
    19203: ("lea", "0x1(%rbx),%rdx"),
    19208: ("mov", "%rax,0xd631(%rip)"),
    19215: ("lea", "0xd62a(%rip),%rcx"),
    19222: ("mov", "$0x1,%eax"),
    19227: ("mov", "%ax,0xd62e(%rip)"),
    19234: ("mov", "%rcx,%rax"),
    19237: ("mov", "%rdx,0xd604(%rip)"),
    19244: ("mov", "%rdx,0xd615(%rip)"),
    19397: ("mov", "0xd51c(%rip),%rbx"),
    19404: ("cmp", "$0xffffffffffffffff,%rbx"),
    19408: (
        "je",
        "4c9f "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE4openEv+0xdf>",
    ),
    19414: ("cmpb", "$0x0,0xd54b(%rip)"),
    19421: (
        "jne",
        "4c9f "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE4openEv+0xdf>",
    ),
    19427: ("cmpb", "$0x0,0xd53f(%rip)"),
    19434: (
        "jne",
        "4c9f "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE4openEv+0xdf>",
    ),
    19445: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    19450: ("test", "%al,%al"),
    19452: (
        "je",
        "4c9f "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE4openEv+0xdf>",
    ),
    19532: ("add", "$0x1,%rbx"),
    19536: ("mov", "%rsi,0xd4a9(%rip)"),
    19545: ("mov", "%rax,0x10(%rdi)"),
    19565: ("mov", "%rax,0x18(%rdi)"),
    19572: ("mov", "%rbx,0xd46d(%rip)"),
    19579: ("mov", "%rbx,0xd486(%rip)"),
    19586: ("mov", "%rcx,(%rdi)"),
    19589: ("mov", "%rbx,0x8(%rdi)"),
    19600: ("movw", "$0x1,0xd48f(%rip)"),
    28256: ("lea", "0xd0(%rsp),%rdi"),
    28264: ("mov", "%rax,%rbx"),
    28267: ("mov", "%rdx,%rbp"),
    28275: ("mov", "0xe0(%rsp),%rax"),
    28283: ("mov", "0xe8(%rsp),%rdi"),
    28299: ("mov", "0xd0(%rsp),%r12"),
    28307: ("mov", "0xd8(%rsp),%r13"),
    28409: ("cmpb", "$0x0,0xb1e0(%rip)"),
    28416: ("jne", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    28504: ("cmp", "0xb1b9(%rip),%rcx"),
    28511: ("jne", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    28522: ("cmp", "0xb1af(%rip),%rax"),
    28529: ("jne", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    28535: ("mov", "0x110(%rsp),%rax"),
    28543: ("sub", "$0x1b8,%rax"),
    28549: ("cmp", "$0x248,%rax"),
    28555: ("ja", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    28561: ("mov", "0x118(%rsp),%rax"),
    28569: ("sub", "$0x92,%rax"),
    28575: ("cmp", "$0x26e,%rax"),
    28581: ("ja", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    28587: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    28592: ("test", "%al,%al"),
    28594: ("je", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    28600: ("mov", "0xb229(%rip),%r9"),
    28619: ("test", "%r9,%r9"),
    28622: ("jne", "7c6d <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x206d>"),
    31711: ("cmp", "%rax,0xa532(%rip)"),
    31725: ("jne", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
    31732: ("cmp", "%rax,0xa525(%rip)"),
    31739: ("jne", "7c57 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x2057>"),
}

PIXEL_OPERATIONS = {
    21806: ("mov", "0xccbb(%rip),%r10d"),
    21813: ("test", "%r10d,%r10d"),
    21816: ("je", "5550 <__au_runtime_display_pixel+0x30>"),
    21840: ("mov", "%rdi,%rbx"),
    21843: ("mov", "%rsi,%rbp"),
    21846: ("mov", "%rdx,%r12"),
    21849: ("mov", "%rcx,%r15"),
    21852: ("mov", "%r8,%r14"),
    21855: ("mov", "%r9,%r13"),
    21858: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    21863: ("test", "%al,%al"),
    21865: ("je", "553a <__au_runtime_display_pixel+0x1a>"),
    21867: ("xor", "%edx,%edx"),
    21869: ("mov", "%rbp,%rsi"),
    21872: ("mov", "%rbx,%rdi"),
    21875: ("movl", "$0x2,0xcc73(%rip)"),
    21898: ("movb", "$0x1,0xcb98(%rip)"),
    21905: ("or", "%r13,%rax"),
    21908: ("or", "%r14,%rax"),
    21917: ("ja", "586e <__au_runtime_display_pixel+0x34e>"),
    21923: ("cmp", "0xcb6e(%rip),%r12"),
    21930: ("jae", "5738 <__au_runtime_display_pixel+0x218>"),
    21936: ("cmp", "0xcb69(%rip),%r15"),
    21943: ("jae", "5738 <__au_runtime_display_pixel+0x218>"),
    21949: ("call", "3ef0 <_ZN6aurora4uefi12_GLOBAL__N_1L5quietEv>"),
    21954: ("test", "%al,%al"),
    21956: ("je", "5720 <__au_runtime_display_pixel+0x200>"),
    21962: ("cmpl", "$0x2,0xcc1f(%rip)"),
    21969: ("jne", "5720 <__au_runtime_display_pixel+0x200>"),
    21981: ("cmp", "%rcx,%r12"),
    21984: ("jae", "5778 <__au_runtime_display_pixel+0x258>"),
    21996: ("cmp", "%rax,%r15"),
    21999: ("jae", "5778 <__au_runtime_display_pixel+0x258>"),
    22016: ("imul", "%r15,%rdx"),
    22020: ("add", "%r12,%rdx"),
    22023: ("shl", "$0x2,%rdx"),
    22027: ("mov", "%al,0x40(%rsp)"),
    22031: ("test", "%al,%al"),
    22033: ("je", "5884 <__au_runtime_display_pixel+0x364>"),
    22113: ("call", "1810 <_ZNK6aurora4uefi10PageTables5entryEm>"),
    22138: ("and", "$0xffffffffffffff9f,%rax"),
    22142: ("cmp", "%rdx,%rsi"),
    22145: ("jb", "5790 <__au_runtime_display_pixel+0x270>"),
    22151: ("cmp", "0xcb0a(%rip),%rdx"),
    22158: ("jae", "5790 <__au_runtime_display_pixel+0x270>"),
    22199: ("cmp", "%rdx,%rax"),
    22202: ("jne", "58a6 <__au_runtime_display_pixel+0x386>"),
    22222: ("ja", "5895 <__au_runtime_display_pixel+0x375>"),
    22286: ("mov", "$0x1,%edx"),
    22291: ("mov", "%rbp,%rsi"),
    22294: ("mov", "%rbx,%rdi"),
    22328: ("mov", "$0x1,%edx"),
    22333: ("mov", "%rbp,%rsi"),
    22336: ("mov", "%rbx,%rdi"),
    22339: ("mov", "$0x1,%r12d"),
    22345: (
        "call",
        "4b40 "
        "<_ZN6aurora7display7SessionINS_4uefi12_GLOBAL__N_116DisplayTransportENS3_15ServicePlatformEE8validateEPKvmb>",
    ),
    22350: ("movb", "$0x0,0xc9d4(%rip)"),
    22360: ("movl", "$0x0,0xca8e(%rip)"),
    22392: ("movq", "$0x0,0x40(%rsp)"),
    22401: ("xor", "%eax,%eax"),
    22403: ("xor", "%edx,%edx"),
    22405: ("jmp", "560b <__au_runtime_display_pixel+0xeb>"),
    22446: ("cmp", "%rcx,%r12"),
    22449: ("jae", "5840 <__au_runtime_display_pixel+0x320>"),
    22455: ("mov", "0xc9e7(%rip),%eax"),
    22461: ("cmp", "%rax,%r15"),
    22464: ("jae", "5840 <__au_runtime_display_pixel+0x320>"),
    22466: ("mov", "0xc9e0(%rip),%eax"),
    22477: ("imul", "%r15,%rax"),
    22481: ("add", "%r12,%rax"),
    22484: ("shl", "$0x2,%rax"),
    22493: ("cmpb", "$0x0,0x60(%rsp)"),
    22498: ("je", "5708 <__au_runtime_display_pixel+0x1e8>"),
    22504: ("mov", "0xc9a9(%rip),%rcx"),
    22511: ("sub", "$0x4,%rcx"),
    22515: ("cmp", "%rax,%rcx"),
    22518: ("jb", "5708 <__au_runtime_display_pixel+0x1e8>"),
    22524: ("mov", "0xc9aa(%rip),%ecx"),
    22530: ("shl", "$0x8,%r13d"),
    22534: ("test", "%ecx,%ecx"),
    22536: ("jne", "5860 <__au_runtime_display_pixel+0x340>"),
    22538: ("mov", "0xb0(%rsp),%ecx"),
    22545: ("shl", "$0x10,%ecx"),
    22548: ("or", "%ecx,%r14d"),
    22551: ("or", "%r14d,%r13d"),
    22582: ("jmp", "570e <__au_runtime_display_pixel+0x1ee>"),
    22624: ("shl", "$0x10,%r14d"),
    22628: ("or", "0xb0(%rsp),%r14d"),
    22636: ("jmp", "5817 <__au_runtime_display_pixel+0x2f7>"),
}

DIAGNOSTIC_PREHEADERS = {
    16685: ("movl", "$0x0,0x1c(%rsp)"),
    16693: ("lea", "0xc(%rsp),%rsi"),
    16698: ("mov", "0xe0a7(%rip),%rcx"),
    16705: ("xor", "%r9d,%r9d"),
    16708: ("movq", "$0x0,0xc(%rsp)"),
    16717: ("mov", "%rsi,%r8"),
    16720: ("movabs", "$0xcccccccccccccccd,%r10"),
    16730: ("movq", "$0x0,0x14(%rsp)"),
    17002: ("movq", "$0x0,0xc(%rsp)"),
    17011: ("mov", "%rsi,%r8"),
    17014: ("xor", "%r9d,%r9d"),
    17017: ("mov", "0xdf60(%rip),%rcx"),
    17024: ("movq", "$0x0,0x14(%rsp)"),
    17033: ("movabs", "$0xcccccccccccccccd,%r10"),
    17043: ("movl", "$0x0,0x1c(%rsp)"),
    17322: ("movq", "$0x0,0xc(%rsp)"),
    17331: ("mov", "%rsi,%r8"),
    17334: ("xor", "%r9d,%r9d"),
    17337: ("mov", "0xde18(%rip),%rcx"),
    17344: ("movq", "$0x0,0x14(%rsp)"),
    17353: ("movabs", "$0xcccccccccccccccd,%r10"),
    17363: ("movl", "$0x0,0x1c(%rsp)"),
    17642: ("movq", "$0x0,0xc(%rsp)"),
    17651: ("mov", "%rsi,%r8"),
    17654: ("xor", "%r9d,%r9d"),
    17657: ("mov", "0xdcf8(%rip),%rcx"),
    17664: ("movq", "$0x0,0x14(%rsp)"),
    17673: ("movabs", "$0xcccccccccccccccd,%r10"),
    17683: ("movl", "$0x0,0x1c(%rsp)"),
    17962: ("movq", "$0x0,0xc(%rsp)"),
    17971: ("mov", "%rsi,%r8"),
    17974: ("xor", "%r9d,%r9d"),
    17977: ("mov", "0xdb90(%rip),%rcx"),
    17984: ("movq", "$0x0,0x14(%rsp)"),
    17993: ("movabs", "$0xcccccccccccccccd,%r10"),
    18003: ("movl", "$0x0,0x1c(%rsp)"),
    18282: ("movq", "$0x0,0xc(%rsp)"),
    18291: ("mov", "%rsi,%r8"),
    18294: ("xor", "%r9d,%r9d"),
    18297: ("mov", "0xda90(%rip),%rcx"),
    18304: ("movq", "$0x0,0x14(%rsp)"),
    18313: ("movabs", "$0xcccccccccccccccd,%r10"),
    18323: ("movl", "$0x0,0x1c(%rsp)"),
    18602: ("movq", "$0x0,0xc(%rsp)"),
    18611: ("mov", "%rsi,%r8"),
    18614: ("xor", "%r9d,%r9d"),
    18617: ("mov", "0xd900(%rip),%rcx"),
    18624: ("movq", "$0x0,0x14(%rsp)"),
    18633: ("movabs", "$0xcccccccccccccccd,%r10"),
    18643: ("movl", "$0x0,0x1c(%rsp)"),
    29325: ("mov", "0xaf7c(%rip),%rcx"),
    29332: ("mov", "%r14,%rdi"),
    29335: ("xor", "%r8d,%r8d"),
    29338: ("movq", "$0x0,0xb8(%rsp)"),
    29350: ("movq", "$0x0,0xc0(%rsp)"),
    29362: ("movabs", "$0xcccccccccccccccd,%rbx"),
    29372: ("movl", "$0x0,0xc8(%rsp)"),
    29677: ("mov", "0xae04(%rip),%rcx"),
    29684: ("mov", "%r14,%rdi"),
    29687: ("xor", "%r8d,%r8d"),
    29690: ("movq", "$0x0,0xb8(%rsp)"),
    29702: ("movq", "$0x0,0xc0(%rsp)"),
    29714: ("movabs", "$0xcccccccccccccccd,%rbx"),
    29724: ("movl", "$0x0,0xc8(%rsp)"),
    29997: ("mov", "0xacb4(%rip),%rcx"),
    30004: ("mov", "%r14,%rdi"),
    30007: ("xor", "%r8d,%r8d"),
    30010: ("movq", "$0x0,0xb8(%rsp)"),
    30022: ("movq", "$0x0,0xc0(%rsp)"),
    30034: ("movabs", "$0xcccccccccccccccd,%rbx"),
    30044: ("movl", "$0x0,0xc8(%rsp)"),
    30317: ("mov", "0xab6c(%rip),%rcx"),
    30324: ("mov", "%r14,%rdi"),
    30327: ("xor", "%r8d,%r8d"),
    30330: ("movq", "$0x0,0xb8(%rsp)"),
    30342: ("movq", "$0x0,0xc0(%rsp)"),
    30354: ("movabs", "$0xcccccccccccccccd,%rbx"),
    30364: ("movl", "$0x0,0xc8(%rsp)"),
    30637: ("mov", "0xaa24(%rip),%rcx"),
    30644: ("mov", "%r14,%rdi"),
    30647: ("xor", "%r8d,%r8d"),
    30650: ("movq", "$0x0,0xb8(%rsp)"),
    30662: ("movq", "$0x0,0xc0(%rsp)"),
    30674: ("movabs", "$0xcccccccccccccccd,%rbx"),
    30684: ("movl", "$0x0,0xc8(%rsp)"),
    30957: ("mov", "0xa8dc(%rip),%rcx"),
    30964: ("mov", "%r14,%rdi"),
    30967: ("xor", "%r8d,%r8d"),
    30970: ("movq", "$0x0,0xb8(%rsp)"),
    30982: ("movq", "$0x0,0xc0(%rsp)"),
    30994: ("movabs", "$0xcccccccccccccccd,%rbx"),
    31004: ("movl", "$0x0,0xc8(%rsp)"),
    31277: ("movq", "$0x0,0xb8(%rsp)"),
    31289: ("mov", "0xa780(%rip),%rcx"),
    31296: ("mov", "%r14,%rdi"),
    31299: ("movabs", "$0xcccccccccccccccd,%r8"),
    31309: ("movq", "$0x0,0xc0(%rsp)"),
    31321: ("movl", "$0x0,0xc8(%rsp)"),
    16916: ("mov", "$0x3f8,%ebp"),
    24476: ("lea", "0xb8(%rsp),%r14"),
    28619: ("test", "%r9,%r9"),
    28622: ("jne", "7c6d <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x206d>"),
    28631: ("mov", "%r9,0x30(%rsp)"),
    28886: ("mov", "0x30(%rsp),%r9"),
    28931: ("mov", "%r9,0x20(%rsp)"),
    29074: ("mov", "0x20(%rsp),%r9"),
    25869: ("lea", "0x9b34(%rip),%r11"),
    26392: ("mov", "%r11,0x18(%rsp)"),
    26426: ("mov", "0x18(%rsp),%r11"),
    26731: ("mov", "%r11,0x40(%rsp)"),
    26824: ("mov", "0x40(%rsp),%r11"),
    27519: ("mov", "%r11,0x18(%rsp)"),
    27568: ("mov", "0x18(%rsp),%r11"),
    28188: ("mov", "%r11,0x18(%rsp)"),
    28222: ("mov", "0x18(%rsp),%r11"),
    28246: ("mov", "%r11,0x28(%rsp)"),
    28328: ("mov", "0x28(%rsp),%r11"),
    28440: ("mov", "%r11,0x38(%rsp)"),
    28614: ("mov", "0x38(%rsp),%r11"),
    28636: ("mov", "%r11,0x28(%rsp)"),
    28926: ("mov", "%r11,0x18(%rsp)"),
    29069: ("mov", "0x18(%rsp),%r11"),
    31412: ("mov", "$0x3f8,%ebp"),
    26259: ("mov", "$0x3f8,%ebp"),
    26272: ("movzbl", "(%r9),%r10d"),
    26337: ("add", "$0x1,%r9"),
    26348: ("cmp", "%r9,%rax"),
    26351: ("jne", "66a0 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0xaa0>"),
    31504: ("movzbl", "(%r11),%r9d"),
    31572: ("add", "$0x1,%r11"),
    31583: ("cmp", "%r11,%rax"),
    31586: ("jne", "7b10 <_ZN6aurora4uefi21run_graphical_consoleEmRKNS0_5BytesE+0x1f10>"),
    31588: ("nop", ""),
    31589: ("data16", "cs nopw 0x0(%rax,%rax,1)"),
}


# The mapped-address and color value definitions feeding the checked predicates.
PIXEL_OPERATIONS.update(
    {
        21890: ("mov", "0xb0(%rsp),%rax"),
        21975: ("mov", "0xcbc3(%rip),%ecx"),
        21990: ("mov", "0xcbb8(%rip),%eax"),
        22005: ("mov", "0xcbad(%rip),%edx"),
        22039: ("and", "$0xfffffffffffff000,%rdx"),
        22046: ("lea", "0x58(%rsp),%rdi"),
        22051: ("mov", "%rcx,0x10(%rsp)"),
        22056: ("movabs", "$0xffffa00000001000,%rax"),
        22066: ("lea", "(%rdx,%rax,1),%rsi"),
        22070: ("mov", "0xcbe3(%rip),%rax"),
        22077: ("mov", "%rdx,0x8(%rsp)"),
        22082: ("mov", "%rsi,0x18(%rsp)"),
        22087: ("mov", "%rax,0x58(%rsp)"),
        22092: ("mov", "0xcbad(%rip),%rax"),
        22099: ("movq", "$0x0,0x68(%rsp)"),
        22108: ("mov", "%rax,0x60(%rsp)"),
        22118: ("mov", "0x8(%rsp),%rdx"),
        22123: ("mov", "0x10(%rsp),%rcx"),
        22128: ("movabs", "$0x5fffffffefff,%rsi"),
        22164: ("movabs", "$0x5ffffffff000,%rdx"),
        22174: ("movabs", "$0x800000000000001b,%rsi"),
        22184: ("add", "0xcad1(%rip),%rdx"),
        22191: ("add", "0x18(%rsp),%rdx"),
        22196: ("or", "%rsi,%rdx"),
        22472: ("movb", "$0x1,0x60(%rsp)"),
        22488: ("mov", "%rax,0x58(%rsp)"),
        22524: ("mov", "0xc9aa(%rip),%ecx"),
        22538: ("mov", "0xb0(%rsp),%ecx"),
        22545: ("shl", "$0x10,%ecx"),
        22548: ("or", "%ecx,%r14d"),
        22551: ("or", "%r14d,%r13d"),
        22561: ("movabs", "$0xffffa00000001000,%rcx"),
        22592: ("movq", "$0x0,0x58(%rsp)"),
        22601: ("movq", "$0x0,0x60(%rsp)"),
        22610: ("jmp", "5708 <__au_runtime_display_pixel+0x1e8>"),
        22624: ("shl", "$0x10,%r14d"),
        22628: ("or", "0xb0(%rsp),%r14d"),
        22636: ("jmp", "5817 <__au_runtime_display_pixel+0x2f7>"),
    }
)

DIAGNOSTIC_PREHEADERS[0x70C3] = ("mov", "0x28(%rsp),%r11")


# Real close arguments and disjoint 32-byte Display::open return area.
AUTHORITY_OPERATIONS.update(
    {
        31617: ("mov", "%rbp,%rsi"),
        31620: ("mov", "%rbx,%rdi"),
        31635: ("mov", "%rbp,%rsi"),
        31638: ("mov", "%rbx,%rdi"),
        31677: ("mov", "%rax,%rbx"),
        31680: ("mov", "%rdx,%rbp"),
        31690: ("mov", "%r13,%rsi"),
        31693: ("mov", "%r12,%rdi"),
        31706: ("mov", "0x18(%rsp),%rax"),
        31727: ("mov", "0x20(%rsp),%rax"),
        31741: ("mov", "%r13,%rsi"),
        31744: ("mov", "%r12,%rdi"),
        31757: ("lea", "0xd0(%rsp),%rdi"),
        31779: ("mov", "0xe0(%rsp),%rax"),
        31792: ("mov", "0xd0(%rsp),%r12"),
        31800: ("mov", "0xd8(%rsp),%r13"),
        31808: ("mov", "%rax,0x18(%rsp)"),
        31813: ("mov", "0xe8(%rsp),%rax"),
        31821: ("mov", "%rax,0x20(%rsp)"),
    }
)


class Proof:
    def __init__(self, checker, decoder, linked, code, payload):
        self.c, self.d, self.linked, self.code, self.payload = checker, decoder, linked, code, payload
        self.need = checker.need

    def rows(self, name):
        return self.c.paired_rows(self.linked.functions[name], self.code)

    def expect(self, expected):
        self.c.capture_expect(self.code, expected)

    def rip(self, address, target, operation=None, prefix=None, suffix=None):
        row = self.code[address]
        self.need(self.c.capture_rip_target(row, self.payload) == target, "GCC16 capture RIP identity changed")
        self.need(operation is None or row.op == operation, "GCC16 capture state operation changed")
        self.need(prefix is None or row.args.startswith(prefix), "GCC16 capture state source changed")
        self.need(suffix is None or row.args.endswith(suffix), "GCC16 capture state destination changed")

    def edge(self, address, operation, target):
        row = self.code[address]
        self.need(row.op == operation and self.d.target_of(row) == target, "GCC16 capture edge changed")

    def call(self, address, target):
        self.edge(address, "call", target)

    def writers(self, target, count, expected):
        self.need(
            self.c.capture_direct_writers(self.d, self.code, self.payload, target, count) == expected,
            "GCC16 capture state writer inventory changed",
        )

    def cfg(self, name):
        rows = self.rows(name)
        addresses = {r.address for r in rows}
        edges, parents = {}, {a: set() for a in addresses}
        for row in rows:
            targets = set()
            if row.op in self.d.BRANCHES:
                target = self.d.target_of(row)
                self.need(target in addresses, "GCC16 capture local branch escaped its owner")
                targets.add(target)
            terminal = row.op in ("ret", "ud2", "jmp") or (
                row.op == "call" and self.d.target_of(row) in (0x3FE0, 0x4A50)
            )
            if not terminal and row.next in addresses:
                targets.add(row.next)
            edges[row.address] = targets
            for target in targets:
                parents[target].add(row.address)
        entry = self.linked.functions[name].address
        reachable, pending = set(), [entry]
        while pending:
            address = pending.pop()
            if address not in reachable:
                reachable.add(address)
                pending.extend(edges[address])
        dom = {a: ({a} if a == entry else set(reachable)) for a in reachable}
        changed = True
        while changed:
            changed = False
            for address in sorted(reachable - {entry}):
                incoming = parents[address] & reachable
                self.need(bool(incoming), "GCC16 capture reachable node has no predecessor")
                value = {address} | set.intersection(*(dom[p] for p in incoming))
                if dom[address] != value:
                    dom[address], changed = value, True
        return edges, dom

    def dominates(self, dom, target, required):
        self.need(target in dom and set(required) <= dom[target], "GCC16 capture required predicates do not dominate")

    def selector(self):
        self.expect({0x65A5: ("mov", "$0x10,%edi"), 0x6B40: ("mov", "$0x18,%edi"), 0x6B64: ("mov", "$0x13,%edi")})
        for address, target, text in (
            (0x65AA, 0x104AF, "capture selector"),
            (0x6B45, 0x104C0, "capture release deadline"),
            (0x6B69, 0x1049B, "capture UART status"),
        ):
            self.rip(address, target, "lea", suffix=",%rsi")
            self.c.capture_readonly(self.linked, target, len(text) + 1)
            self.need(
                self.payload[target : target + len(text) + 1] == text.encode() + b"\0",
                "GCC16 selector failure reason changed",
            )
        self.expect(
            {
                0x6571: ("mov", "$0x989680,%ecx"),
                0x6576: ("mov", "$0x3fd,%edx"),
                0x6580: ("pause", ""),
                0x6582: ("sub", "$0x1,%ecx"),
                0x658B: ("in", "(%dx),%al"),
                0x658C: ("test", "$0x1e,%al"),
                0x6594: ("test", "$0x1,%al"),
                0x6598: ("mov", "$0x3f8,%edx"),
                0x659D: ("in", "(%dx),%al"),
                0x659E: ("sub", "$0x43,%eax"),
                0x65A1: ("cmp", "$0x21,%al"),
                0x65D1: ("movzbl", "%al,%eax"),
                0x65DB: ("movzbl", "(%rdx,%rax,1),%ebp"),
                0x65DF: ("test", "%bpl,%bpl"),
                0x6683: ("lea", "0x30(%rbp),%eax"),
                0x6686: ("mov", "$0x3f8,%edx"),
                0x668B: ("out", "%al,(%dx)"),
            }
        )
        for item in (
            (0x6585, "je", 0x6B40),
            (0x658E, "jne", 0x6B64),
            (0x6596, "je", 0x6580),
            (0x65A3, "jbe", 0x65D1),
            (0x65E2, "je", 0x65A5),
        ):
            self.edge(*item)
        for address in (0x65B1, 0x6B4C, 0x6B70):
            self.call(address, 0x3FE0)
        self.rip(0x65D4, 0x10880, "lea", suffix=",%rdx")
        self.c.capture_readonly(self.linked, 0x10880, 34)
        table = self.payload[0x10880:0x108A2]
        expected = {ord("G"): 1, ord("C"): 2, ord("D"): 3, ord("c"): 4, ord("d"): 5, ord("F"): 6, ord("I"): 7}
        for byte in range(256):
            index = (byte - 0x43) & 255
            self.need((table[index] if index <= 33 else 0) == expected.get(byte, 0), "GCC16 capture selector changed")
        self.rip(0x65E4, 0x121C8, "mov", "%bpl,")
        self.writers(0x121C8, 1, [0x65E4])
        # EBP is zero-extended from the closed table, preserved through the fully
        # inventoried inline release-label loop, and converted to one ASCII digit.
        for row in self.rows(RUN):
            if 0x65DB < row.address < 0x6683:
                args = self.d.arguments(row.args)
                self.need(row.op != "call", "GCC16 capture release acquired a callee")
                self.need(
                    not (args and self.c.paired_register(args[-1]) == "rbp" and row.op not in self.d.READ_ONLY),
                    "GCC16 selector value clobbered",
                )
        _, dom = self.cfg(RUN)
        self.dominates(
            dom,
            0x6E5B,
            [0x625E, 0x626B, 0x658B, 0x658C, 0x6594, 0x659D, 0x659E, 0x65A1, 0x65D1, 0x65DB, 0x65DF, 0x65E4, 0x66E1],
        )
        return dict(
            selectors={chr(k): v for k, v in expected.items()},
            invalid_bytes=249,
            sampling_limit=10000000,
            table=[0x10880, 34],
            writer=0x65E4,
            release_digit=0x6683,
            release_before_first_open=0x6E5B,
        )

    def authority(self):
        self.expect(AUTHORITY_OPERATIONS)
        self.call(0x4A60, 0x3FE0)
        display_writes = []
        for row in self.rows(DISPLAY + "4openEv"):
            arguments = self.d.arguments(row.args)
            if (
                arguments
                and "(" in arguments[-1]
                and "%rip" not in arguments[-1]
                and "%rsp" not in arguments[-1]
                and row.op not in self.d.READ_ONLY | {"lea"}
            ):
                display_writes.append(row.address)
        self.need(
            display_writes == [0x4C59, 0x4C6D, 0x4C82, 0x4C85], "GCC16 Display open acquired an indirect record writer"
        )
        edges, dom = self.cfg(RUN)
        for address, target in (
            (0x6E5B, 0x4AD0),
            (0x6E6E, 0x4BC0),
            (0x6F1D, 0x4A70),
            (0x6F4E, 0x4B40),
            (0x7B8E, 0x4A70),
            (0x7BA5, 0x4A70),
            (0x7BB3, 0x4AD0),
            (0x7BD5, 0x4B40),
            (0x7C08, 0x4B40),
            (0x7C1E, 0x4BC0),
            (0x6FEC, 0xF3AC),
        ):
            self.call(address, target)
        self.expect(
            {
                0x5F6E: ("lea", "0xf0(%rsp),%r15"),
                0x6FD4: ("mov", "%r15,%rdi"),
                0x6F06: ("mov", "0xf8(%rsp),%rsi"),
                0x6F0E: ("mov", "0xf0(%rsp),%rdi"),
                0x6F16: ("xor", "%edx,%edx"),
                0x6F2A: ("xor", "%edx,%edx"),
                0x6F34: ("mov", "0x108(%rsp),%rsi"),
                0x6F3C: ("mov", "0x100(%rsp),%rdi"),
                0x6EC1: ("cmp", "$0x2,%al"),
                0x6EE1: ("cmp", "$0x3,%al"),
                0x6EE9: ("cmp", "$0x4,%al"),
                0x6EF1: ("cmp", "$0x5,%al"),
                0x7B87: ("xor", "%edx,%edx"),
                0x7B99: ("mov", "$0x1,%edx"),
                0x7BC8: ("xor", "%edx,%edx"),
                0x7C03: ("mov", "$0x1,%edx"),
            }
        )
        for item in ((0x6EDB, "je", 0x7022), (0x6EE3, "je", 0x7B74), (0x6EEB, "je", 0x7B81), (0x6EF3, "je", 0x7BC8)):
            self.edge(*item)
        reaches = {0x6FEC}
        while True:
            larger = reaches | {a for a, t in edges.items() if t & reaches}
            if reaches == larger:
                break
            reaches = larger
        expected = {
            0x6E83: (0xF0, "%rbx"),
            0x6E9B: (0xF8, "%rbp"),
            0x6EAD: (0x110, "%rax"),
            0x6EC3: (0x100, "%r12"),
            0x6ECB: (0x108, "%r13"),
            0x6ED3: (0x118, "%rdi"),
            0x7022: (0xF0, "%r12"),
            0x7B74: (0x100, "%rbx"),
        }
        observed = {}
        for row in self.rows(RUN):
            if row.address not in reaches or not 0x5F6E < row.address:
                continue
            args = self.d.arguments(row.args)
            if row.op in self.d.READ_ONLY | {"lea", "nop", "nopl", "nopw", "cs", "data16"} or len(args) != 2:
                continue
            self.need(self.c.paired_register(args[-1]) != "r15", "GCC16 capture record pointer clobbered")
            slot = self.c.paired_slot(args[-1])
            if row.address >= 0x6E5B and slot is not None and slot < 0x120:
                width = self.c.paired_width(row, args)
                if 0xF0 < slot + width:
                    self.need(width == 8, "GCC16 capture partial record write")
                    observed[row.address] = (slot, args[0])
        self.need(observed == expected, "GCC16 capture record writers changed")
        for clear, target, reopen, pre in (
            (0x7BAA, 0x12150, 0x7BB3, [0x7B8E, 0x7B9E, 0x7BA5]),
            (0x7C15, 0x12128, 0x7C1E, [0x7BD5, 0x7BDF, 0x7BE6, 0x7BF4, 0x7C08]),
        ):
            self.rip(clear, target, "movw", "$0x0,")
            self.dominates(dom, reopen, pre + [clear])
        self.rip(0x7B9E, 0x12151, "movb", "$0x1,")
        self.rip(0x7BE6, 0x12129, "movb", "$0x1,")
        for target, writer in ((0x12130, 0x4B25), (0x120E8, 0x4C74), (0x12148, 0x4B2C), (0x12108, 0x4C7B)):
            self.writers(target, 8, [writer])
        self.expect(
            {
                0x4AD8: ("cmp", "$0xffffffffffffffff,%rbx"),
                0x4B03: ("lea", "0x1(%rbx),%rdx"),
                0x4BCC: ("cmp", "$0xffffffffffffffff,%rbx"),
                0x4C4C: ("add", "$0x1,%rbx"),
                0x4A7B: ("cmp", "%rax,%rdi"),
                0x4A8A: ("cmp", "%rax,(%rdi)"),
                0x4B48: ("cmp", "%rax,%rdi"),
                0x4B5A: ("cmp", "%rax,(%rdi)"),
            }
        )
        for name, identity, deref, checks, ret, overflow, advance, store in (
            (
                CONSOLE,
                0x4A7B,
                0x4A8A,
                [0x4A8A, 0x4A8F, 0x4A95, 0x4A9A, 0x4A9F, 0x4AA8, 0x4AB3],
                0x4ABB,
                0x4AD8,
                0x4B03,
                0x4B25,
            ),
            (
                DISPLAY,
                0x4B48,
                0x4B5A,
                [0x4B5A, 0x4B5F, 0x4B65, 0x4B6A, 0x4B6F, 0x4B78, 0x4B83, 0x4B8B, 0x4B90, 0x4B9F, 0x4BAE],
                0x4BB8,
                0x4BCC,
                0x4C4C,
                0x4C74,
            ),
        ):
            _, validation = self.cfg(name + "8validateEPKvmb")
            self.dominates(validation, deref, [identity])
            self.dominates(validation, ret, [identity] + checks)
            _, opening = self.cfg(name + "4openEv")
            self.dominates(opening, store, [overflow, advance])
        self.rip(0x4A70, 0x12140, "lea", suffix=",%rax")
        self.rip(0x4B40, 0x12100, "lea", suffix=",%rax")
        self.dominates(
            dom,
            0x6FEC,
            [
                0x5F6E,
                0x65E4,
                0x6E5B,
                0x6E6E,
                0x6F1D,
                0x6F4E,
                0x6F58,
                0x6F6A,
                0x6F85,
                0x6F9F,
                0x6FB0,
                0x6FCB,
                0x6FD4,
                0x6FE1,
            ],
        )
        self.writers(0x121E8, 8, [0x6FE1])
        return dict(
            record_bytes=48,
            record_stack_offset=0xF0,
            record_pointer=[0x5F6E, 0x6FD4],
            cross_writes=[0x7022, 0x7B74],
            real_reopens=[0x7BB3, 0x7C1E],
            preflights=[0x6F1D, 0x6F4E],
            compiled_entry=0x6FEC,
            stale_record_generations_preserved=[0xF8, 0x108],
            record_writers={hex(k): list(v) for k, v in expected.items()},
        )

    def pixel(self):
        self.expect(PIXEL_OPERATIONS)
        edges, dom = self.cfg(PIXEL)
        self.expect(
            {
                0x5597: ("cmp", "$0xff,%rax"),
                0x56C7: ("cmp", "$0xf423f,%rdx"),
                0x56DB: ("cmp", "$0xffffffffffffffff,%rax"),
                0x56E5: ("add", "$0x1,%rax"),
                0x56F7: ("cmp", "$0x6,%al"),
                0x56FF: ("test", "%rdx,%rdx"),
                0x57A0: ("cmp", "$0x7,%al"),
                0x57A4: ("cmp", "$0x37,%rdx"),
                0x5708: ("mov", "$0x1,%r12d"),
                0x5755: ("mov", "%r12,%rax"),
                0x581A: ("add", "$0x1,%rdx"),
                0x581E: ("xor", "%r12d,%r12d"),
                0x5821: ("movabs", "$0xffffa00000001000,%rcx"),
                0x582B: ("mov", "%r13d,(%rax,%rcx,1)"),
            }
        )
        for item in (
            (0x56DF, "je", 0x5873),
            (0x56F9, "jne", 0x57A0),
            (0x5702, "jne", 0x57A0),
            (0x57A2, "jne", 0x57AE),
            (0x57A8, "je", 0x5708),
        ):
            self.edge(*item)
        for address, target, operation, prefix, suffix in (
            (0x56C0, 0x121F8, "mov", None, ",%rdx"),
            (0x56D4, 0x121C0, "mov", None, ",%rax"),
            (0x56E9, 0x121C0, "mov", "%rax,", None),
            (0x56F0, 0x121C8, "movzbl", None, ",%eax"),
            (0x582F, 0x121F8, "mov", "%rdx,", None),
        ):
            self.rip(address, target, operation, prefix, suffix)
        self.writers(0x121C0, 8, [0x56E9])
        self.writers(0x121F8, 8, [0x582F])
        self.call(0x557D, 0x4B40)
        self.call(0x5719, 0x4B40)
        self.dominates(
            dom,
            0x582B,
            [
                0x5535,
                0x5567,
                0x557D,
                0x5597,
                0x55A3,
                0x55B0,
                0x55C2,
                0x55CA,
                0x55DD,
                0x560F,
                0x5661,
                0x56B7,
                0x56C7,
                0x56DB,
                0x56E5,
                0x56E9,
                0x56F7,
                0x57A0,
                0x57AE,
                0x57BD,
                0x57DD,
                0x57F3,
                0x581A,
            ],
        )
        reachable, pending = set(), [0x5708]
        while pending:
            address = pending.pop()
            if address not in reachable:
                reachable.add(address)
                pending.extend(edges[address])
        self.need(not {0x581A, 0x582B, 0x582F} & reachable, "GCC16 injected pixel failure reaches a store")
        indirect = []
        for row in self.rows(PIXEL):
            args = self.d.arguments(row.args)
            if row.op not in self.d.READ_ONLY | {"lea", "nop", "nopl", "nopw", "cs", "data16"} and args:
                if "(" in args[-1] and "%rip" not in args[-1] and "%rsp" not in args[-1]:
                    indirect.append(row.address)
        self.need(indirect == [0x582B], "GCC16 pixel acquired an extra indirect store")
        return dict(
            attempt_writer=0x56E9,
            failure_successful_store_ordinals=[0, 55],
            error_join=0x5708,
            mmio_store=0x582B,
            successful_store_counter=0x582F,
            returned_error=1,
            success_order="attempt, fixture predicates, MMIO store, successful counter",
        )

    def uart(self, start, data, port_register=None):
        """Check one exact inlined bounded UART attempt; return its join.

        UART timeout skips that character, as in the source contract. This proves
        the attempted diagnostic sequence, not reliable delivery by hardware.
        """
        rows = [r for a, r in sorted(self.code.items()) if start <= a < start + 160]
        rows = [r for r in rows if r.op not in ("nop", "nopl", "nopw", "cs", "data16")]
        self.need(
            rows[0].op == "mov" and rows[0].args in ("$0xf4240,%esi", "$0xf4240,%edi"),
            "GCC16 UART timeout is not fixed and bounded",
        )
        counter = rows[0].args.split(",")[1]
        self.need(
            rows[1].op == "jmp" and self.d.target_of(rows[1]) == rows[4].address,
            "GCC16 UART initial status edge changed",
        )
        pattern = [
            ("sub", "$0x1," + counter),
            None,
            ("mov", "$0x3fd,%edx"),
            ("in", "(%dx),%al"),
            ("mov", "%eax,%ecx"),
            ("test", "$0x1e,%al"),
            None,
            None,
            ("mov", "$0xffffffc3,%eax"),
            ("mov", "$0x3fa,%edx"),
            ("out", "%al,(%dx)"),
            ("and", "$0xfffffffe,%ecx"),
            ("and", "$0x20,%ecx"),
            None,
            data,
            ("mov", (port_register or "$0x3f8") + ",%edx"),
            ("out", "%al,(%dx)"),
        ]
        for row, expected in zip(rows[2:], pattern):
            if expected is not None:
                self.need((row.op, row.args) == expected, "GCC16 UART instruction/value changed")
        join = rows[18].next
        self.edge(rows[3].address, "je", join)
        self.edge(rows[8].address, "je", rows[14].address)
        self.edge(rows[15].address, "je", rows[2].address)
        self.rip(rows[9].address, 0x12230, "movb", "$0x1,")
        return dict(begin=start, join=join, data=data[1], output=rows[18].address, attempt_limit=1000000)

    def text_loop(self, start, expected, end_register=None):
        row = self.code[start]
        self.need(row.op == "lea", "GCC16 diagnostic text does not start at exact read-only data")
        target = self.c.capture_rip_target(row, self.payload)
        self.c.capture_readonly(self.linked, target, len(expected) + 1)
        self.need(
            self.payload[target : target + len(expected) + 1] == expected.encode("ascii") + b"\0",
            "GCC16 diagnostic label/extent changed",
        )
        pointer = self.d.arguments(row.args)[1]
        rows = [r for a, r in sorted(self.code.items()) if row.next <= a < row.next + 180]
        load = next(r for r in rows if r.op == "movzbl")
        args = self.d.arguments(load.args)
        self.need(args[0] in ("(" + pointer + ")", "0x0(" + pointer + ")"), "GCC16 diagnostic text pointer changed")
        byte = args[1]
        if end_register is None:
            bound = next(r for r in rows if r.op == "lea" and "(" + pointer + ")" in r.args)
            self.need(
                self.d.arguments(bound.args)[0] == hex(len(expected)) + "(" + pointer + ")",
                "GCC16 diagnostic text loop bound changed",
            )
            end_register = self.d.arguments(bound.args)[1]
        attempt = self.uart(
            load.next,
            ("mov", byte + ",%eax"),
            "%ebp" if start in (0x420D, 0x434D, 0x448D, 0x45CD, 0x470D, 0x484D) else None,
        )
        advance = self.code[attempt["join"]]
        self.need((advance.op, advance.args) == ("add", "$0x1," + pointer), "GCC16 diagnostic text does not advance")
        comparison = self.code[advance.next]
        branch = self.code[comparison.next]
        self.need(
            comparison.op == "cmp" and set(self.d.arguments(comparison.args)) == {pointer, end_register},
            "GCC16 diagnostic text termination changed",
        )
        self.edge(branch.address, "jne", load.address)
        return dict(
            text=expected,
            data=target,
            length=len(expected),
            begin=start,
            read=load.address,
            end=branch.next,
            uart=attempt,
        )

    def number_loop(self, load, counter, multiply, magic, count, pointer, base, temporary, port_register=None):
        self.rip(load, counter, "mov", suffix=",%rcx")
        # Unsigned multiply-high by ceil(2**67/10), then >>3 is exact u64 /10.
        # The loop computes remainder n-10*q, writes ASCII, and repeats for n>9.
        # Therefore it emits 1..20 digits into the existing 20-byte private buffer.
        begin = multiply - 11
        before = [r for a, r in sorted(self.code.items()) if load <= a < begin]
        self.need(
            any((r.op, r.args) == ("movabs", "$0xcccccccccccccccd," + magic) for r in before),
            "GCC16 decimal reciprocal changed",
        )
        rows = []
        address = begin
        for _ in range(15):
            rows.append(self.code[address])
            address = rows[-1].next
        expected = [
            ("mov", "%rcx,%rax"),
            ("add", "$0x1," + count),
            ("add", "$0x1," + pointer),
            ("mul", magic),
            ("mov", "%rcx,%rax"),
            ("shr", "$0x3,%rdx"),
            ("lea", "(%rdx,%rdx,4)," + temporary),
            ("add", temporary + "," + temporary),
            ("sub", temporary + ",%rax"),
            ("add", "$0x30,%eax"),
            ("mov", "%al,-0x1(" + pointer + ")"),
            ("mov", "%rcx,%rax"),
            ("mov", "%rdx,%rcx"),
            ("cmp", "$0x9,%rax"),
        ]
        self.need([(r.op, r.args) for r in rows[:14]] == expected, "GCC16 decimal value lineage changed")
        self.edge(rows[14].address, "ja", begin)
        addition = self.code[rows[14].next]
        self.need((addition.op, addition.args) == ("add", base + "," + count), "GCC16 decimal end pointer changed")
        reverse = next(
            r for a, r in sorted(self.code.items()) if addition.next <= a < addition.next + 48 and r.op == "movzbl"
        )
        self.need(self.d.arguments(reverse.args)[0] == "-0x1(" + count + ")", "GCC16 decimal reverse read changed")
        data = self.d.arguments(reverse.args)[1]
        attempt = self.uart(reverse.next, ("mov", data + ",%eax"), port_register)
        decrement = self.code[attempt["join"]]
        comparison = self.code[decrement.next]
        branch = self.code[comparison.next]
        self.need((decrement.op, decrement.args) == ("sub", "$0x1," + count), "GCC16 decimal reverse advance changed")
        self.need(
            comparison.op == "cmp" and set(self.d.arguments(comparison.args)) == {base, count},
            "GCC16 decimal reverse termination changed",
        )
        self.edge(branch.address, "jne", reverse.address)
        return dict(
            counter=counter,
            load=load,
            conversion=begin,
            reverse=reverse.address,
            end=branch.next,
            maximum_digits=20,
            uart=attempt,
        )

    def diagnostics(self):
        self.expect(DIAGNOSTIC_PREHEADERS)
        for name in (FAIL, RUN, self.c.CAPTURE_PLATFORM_FAIL):
            self.need(
                not any(row.op == "ret" for row in self.rows(name)), "GCC16 capture terminal owner acquired a return"
            )
        self.preserve(FAIL, 0x4135, 0x498D, "rsi")
        self.expect({a: ("mov", "$0x3f8,%ebp") for a in (0x4214, 0x4354, 0x4494, 0x45D4, 0x4714, 0x4854)})
        self.preserve(FAIL, 0x4214, 0x498D, "rbp", (0x4354, 0x4494, 0x45D4, 0x4714, 0x4854))
        self.preserve(RUN, 0x5F9C, 0x7AB1, "r14", calls_preserve=True)
        self.preserve(RUN, 0x7192, 0x7A80, "r9")
        self.preserve(RUN, 0x718D, 0x7B10, "r11")
        self.preserve(RUN, 0x6FF1, 0x7223, "r15", calls_preserve=True)
        _, run_dom = self.cfg(RUN)
        self.dominates(run_dom, 0x7A80, [0x6FCB, 0x6FD7, 0x70D6, 0x7103, 0x7192])
        self.dominates(
            run_dom,
            0x7B70,
            [0x717C, 0x717F, 0x71E4, 0x7284, 0x7384, 0x74C4, 0x7604, 0x7744, 0x7884, 0x79C4, 0x7A24, 0x7B01, 0x7B54],
        )
        # Full body inventories close the preheaders and all intervening effects;
        # these checks separately bind every text/counter to its actual UART loop.
        failure_texts = [
            (0x400C, "AURORA_GRAPHICAL_CONSOLE_FAIL: "),
            (0x40CD, " entries="),
            (0x420D, " samples="),
            (0x434D, " output_attempts="),
            (0x448D, " stores="),
            (0x45CD, " completed="),
            (0x470D, " wakes="),
            (0x484D, " pixel_attempts="),
            (0x498D, "\r\n"),
        ]
        failure = [self.text_loop(a, t) for a, t in failure_texts]
        self.expect(
            {
                0x3FE9: ("mov", "%rsi,%rbx"),
                0x3FF1: ("mov", "%rdi,%rbp"),
                0x406D: ("add", "%rbx,%rbp"),
                0x4070: ("cmp", "%rbp,%rbx"),
                0x4075: ("mov", "%rbx,%r9"),
                0x4080: ("movzbl", "(%r9),%r10d"),
                0x40C4: ("add", "$0x1,%r9"),
                0x40C8: ("cmp", "%r9,%rbp"),
            }
        )
        self.edge(0x4073, "je", 0x40CD)
        self.edge(0x40CB, "jne", 0x4080)
        reason = self.uart(0x4084, ("mov", "%r10d,%eax"))
        failure_numbers = []
        for load, counter, multiply in (
            (0x413A, 0x121E8, 0x418B),
            (0x4279, 0x121E0, 0x42CB),
            (0x43B9, 0x121D8, 0x440B),
            (0x44F9, 0x121F8, 0x454B),
            (0x4639, 0x121D0, 0x468B),
            (0x4779, 0x12210, 0x47CB),
            (0x48B9, 0x121C0, 0x490B),
        ):
            failure_numbers.append(self.number_loop(load, counter, multiply, "%r10", "%r9", "%r8", "%rsi", "%rdi"))
        complete_texts = [
            (0x7186, "AURORA_GRAPHICAL_CONSOLE_COMPLETE: completion="),
            (0x722D, " wakes="),
            (0x738D, " stores="),
            (0x74CD, " entries="),
            (0x760D, " samples="),
            (0x774D, " output_attempts="),
            (0x788D, " completed="),
            (0x79CD, " pixel_attempts="),
        ]
        complete = [self.text_loop(a, t) for a, t in complete_texts]
        completion_digit = self.uart(0x71ED, ("lea", "0x30(%r15),%eax"))
        self.expect(
            {
                0x6FF1: ("mov", "%rax,%r15"),
                0x6FF4: ("cmp", "$0x4,%rax"),
                0x717C: ("mfence", ""),
                0x7223: ("lea", "0x30(%r15),%eax"),
            }
        )
        self.edge(0x6FF8, "ja", 0x7C57)
        self.rip(0x717F, 0x12179, "movb", "$0x0,")
        complete_numbers = []
        for load, counter, multiply in (
            (0x728D, 0x12210, 0x730B),
            (0x73ED, 0x121F8, 0x744B),
            (0x752D, 0x121E8, 0x758B),
            (0x766D, 0x121E0, 0x76CB),
            (0x77AD, 0x121D8, 0x780B),
            (0x78ED, 0x121D0, 0x794B),
        ):
            complete_numbers.append(self.number_loop(load, counter, multiply, "%rbx", "%r8", "%rdi", "%r14", "%rsi"))
        complete_numbers.append(self.number_loop(0x7A39, 0x121C0, 0x7A8B, "%r8", "%r9", "%rdi", "%r14", "%rsi", "%ebp"))
        release = self.text_loop(0x65EB, "AURORA_GRAPHICAL_CAPTURE_RELEASED: selector=")
        release_digit = self.uart(0x664D, ("lea", "0x30(%rbp),%eax"))
        # CRLF pointers have one earlier saved/restored definition in the closed
        # run body. The final loop reads exactly two characters from that pointer.
        self.rip(0x650D, 0x10048, "lea", suffix=",%r11")
        self.rip(0x668C, 0x10048, "lea", suffix=",%r9")
        self.rip(0x66E5, 0x1004A, "lea", suffix=",%rax")
        self.rip(0x7B58, 0x1004A, "lea", suffix=",%rax")
        self.c.capture_readonly(self.linked, 0x10048, 3)
        self.need(self.payload[0x10048:0x1004B] == b"\r\n\0", "GCC16 CRLF changed")
        crlf_release = self.uart(0x66A4, ("mov", "%r10d,%eax"), "%ebp")
        crlf_complete = self.uart(0x7B14, ("mov", "%r9d,%eax"))
        self.expect({0x49F0: ("cli", ""), 0x49F1: ("hlt", ""), 0x7B70: ("cli", ""), 0x7B71: ("hlt", "")})
        self.edge(0x49F2, "jmp", 0x49F0)
        self.edge(0x7B72, "jmp", 0x7B70)
        return dict(
            failure=dict(texts=failure, reason=reason, numbers=failure_numbers),
            completion=dict(texts=complete, digit=completion_digit, numbers=complete_numbers, crlf=crlf_complete),
            release=dict(text=release, digit=release_digit, crlf=crlf_release),
            terminal="capture cli/hlt loops",
            delivery="bounded attempts; UART timeout may omit a character",
        )

    def preserve(self, name, begin, end, register, permitted=(), calls_preserve=False):
        for row in self.rows(name):
            if not begin < row.address < end or row.address in permitted:
                continue
            args = self.d.arguments(row.args)
            self.need(row.op != "call" or calls_preserve, "GCC16 capture preserved lineage gained a callee")
            if args and self.c.paired_register(args[-1]) == register:
                self.need(row.op in self.d.READ_ONLY | {"push"}, "GCC16 capture preserved register clobbered")

    def imports(self):
        # Caller-saved inputs are copied into admitted callee-saved registers;
        # each effect requires real Session validation, not merely the same name.
        expected = {
            0x5440: ("mov", "%rdi,%rbp"),
            0x5443: ("mov", "%rsi,%r12"),
            0x5446: ("mov", "%rdx,%rbx"),
            0x5452: ("xor", "%edx,%edx"),
            0x5454: ("mov", "%r12,%rsi"),
            0x5457: ("mov", "%rbp,%rdi"),
            0x54D5: ("mov", "%r12,%rsi"),
            0x54D8: ("mov", "%rbp,%rdi"),
            0x54DB: ("mov", "$0x1,%edx"),
            0x5470: ("cmp", "$0xff,%rbx"),
            0x5484: ("cmp", "$0xffffffffffffffff,%rax"),
            0x4F50: ("mov", "%rdi,%rbx"),
            0x4F53: ("mov", "%rsi,%rbp"),
            0x4F56: ("mov", "%rdx,%r12"),
            0x4F62: ("xor", "%edx,%edx"),
            0x4F64: ("mov", "%rbp,%rsi"),
            0x4F67: ("mov", "%rbx,%rdi"),
            0x4F7D: ("xor", "%edx,%edx"),
            0x4F7F: ("mov", "%rbp,%rsi"),
            0x4F82: ("mov", "%rbx,%rdi"),
            0x501F: ("mov", "$0x1,%edx"),
            0x5024: ("mov", "%rbp,%rsi"),
            0x5027: ("mov", "%rbx,%rdi"),
            0x5099: ("mov", "$0x1,%edx"),
            0x509E: ("mov", "%rbp,%rsi"),
            0x50A1: ("mov", "%rbx,%rdi"),
            0x5036: ("cmp", "$0xffffffffffffffff,%rax"),
            0x50C5: ("cmp", "$0xffffffffffffffff,%rax"),
        }
        self.expect(expected)
        for item in (
            (0x542C, "je", 0x5440),
            (0x5450, "je", 0x542E),
            (0x5477, "ja", 0x5518),
            (0x5488, "je", 0x5507),
            (0x4F36, "je", 0x4F50),
            (0x4F60, "je", 0x4F38),
            (0x503A, "je", 0x53F2),
            (0x50C9, "je", 0x5403),
        ):
            self.edge(*item)
        facts = {}
        layouts = (
            ("__au_runtime_console_put", 0x4A70, [0x5464, 0x54E0], 0x5464, [0x54E0], 0x54FD),
            ("__au_runtime_console_next", 0x4A70, [0x4F6A, 0x4F8F, 0x502A, 0x50A4], 0x4F6A, [0x50A4], 0x50F2),
            (PIXEL, 0x4B40, [0x557D, 0x5719, 0x5749], 0x557D, [0x5719, 0x5749], 0x5770),
        )
        for name, target, calls, preflight, leaves, ret in layouts:
            rows = self.rows(name)
            edges, dom = self.cfg(name)
            self.need(
                [r.address for r in rows if r.op == "call" and self.d.target_of(r) == target] == calls,
                "GCC16 import validator inventory changed",
            )
            self.need([r.address for r in rows if r.op == "ret"] == [ret], "GCC16 import return inventory changed")
            effects = []
            for row in rows:
                args = self.d.arguments(row.args)
                memory_write = (
                    args
                    and "(" in args[-1]
                    and "%rsp" not in args[-1]
                    and row.op not in self.d.READ_ONLY | {"lea", "nop", "nopl", "nopw", "cs", "data16"}
                )
                if row.op in ("in", "out") or memory_write:
                    if row.address in (0x545A, 0x5573):
                        continue  # The source sets private exclusion before Session::enter.
                    effects.append(row.address)
                    self.dominates(dom, row.address, [preflight])
            # Removing all leave checks must disconnect every successful return;
            # pixel has two legitimate leave joins for clipped and ordinary paths.
            reachable, pending = set(), [self.linked.functions[name].address]
            while pending:
                address = pending.pop()
                if address not in reachable and address not in leaves:
                    reachable.add(address)
                    pending.extend(edges[address])
            self.need(ret not in reachable, "GCC16 import return bypasses leave validation")
            facts[name] = dict(validator_calls=calls, effects=effects, return_validation=leaves, return_site=ret)
        return facts


def capture_linked_evidence(checker, decoder, linked, original_code, payload, file_hashes):
    proof = Proof(checker, decoder, linked, original_code, payload)
    proof.need(file_hashes == FILES, "Changed exact GCC16 capture file tuple")
    proof.need(hashlib.sha256(payload).hexdigest() == FILES["payload.bin"], "Changed GCC16 capture payload")
    for row in original_code.values():
        if row.op == "call" or row.op in decoder.BRANCHES:
            decoder.target_of(row)
    named = {s.name: s for s in linked.symbols if s.section}
    for name, identity in STATE.items():
        symbol = named.get(name)
        proof.need(
            symbol is not None and (symbol.address, symbol.size, symbol.section, symbol.kind) == identity,
            "Changed GCC16 capture state identity: " + name,
        )
        proof.need(linked.sections[symbol.section][1] == 8, "GCC16 capture state is not zero-initialized BSS")
    bodies = {}
    for name, (address, size, count, digest) in BODIES.items():
        symbol = linked.functions.get(name)
        proof.need(
            symbol is not None and (symbol.address, symbol.size) == (address, size),
            "Changed GCC16 capture body: " + name,
        )
        rows = proof.rows(name)
        inventory = [[r.address, r.size, r.op, r.args, payload[r.address : r.next].hex()] for r in rows]
        proof.need(
            len(rows) == count and hashlib.sha256(checker.canonical(inventory).encode()).hexdigest() == digest,
            "Changed GCC16 original instruction inventory: " + name,
        )
        bodies[name] = dict(address=address, bytes=size, instructions=count, sha256=digest)
    return dict(
        schema="aurora-graphical-capture-linked-gcc16-v1",
        status="checked-contract-requires-independent-review",
        files=dict(file_hashes),
        original_bodies=bodies,
        original_state={n: list(v) for n, v in STATE.items()},
        selector=proof.selector(),
        authority=proof.authority(),
        pixel=proof.pixel(),
        diagnostics=proof.diagnostics(),
        imports=proof.imports(),
    )
