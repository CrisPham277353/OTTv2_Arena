"""Trusted entry point INSIDE the Linux namespace, before loading submitted code."""
import ctypes
import errno
import resource
import runpy
import sys

# Hard ceilings cannot be raised again by bot code.
for kind, ceiling in [(resource.RLIMIT_AS, 256 * 1024 * 1024), (resource.RLIMIT_CPU, 160),
                      (resource.RLIMIT_FSIZE, 1024 * 1024), (resource.RLIMIT_NOFILE, 64),
                      (resource.RLIMIT_CORE, 0)]:
    resource.setrlimit(kind, (ceiling, ceiling))
lib = ctypes.CDLL('libseccomp.so.2')
lib.seccomp_init.argtypes = [ctypes.c_uint32]
lib.seccomp_init.restype = ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype = ctypes.c_int
lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
lib.seccomp_load.argtypes = [ctypes.c_void_p]
lib.seccomp_release.argtypes = [ctypes.c_void_p]
ctx = lib.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
if not ctx:
    raise RuntimeError('Cannot initialize seccomp')
try:
    for syscall in ('fork', 'vfork', 'clone', 'clone3', 'execve', 'execveat', 'socket', 'socketpair',
                    'connect', 'bind', 'listen', 'accept', 'accept4', 'ptrace', 'process_vm_readv',
                    'process_vm_writev', 'mount', 'umount2', 'unshare', 'setns', 'bpf', 'perf_event_open',
                    'userfaultfd', 'io_uring_setup', 'io_uring_enter', 'io_uring_register',
                    'setrlimit', 'prlimit64', 'reboot', 'kexec_load', 'init_module', 'finit_module',
                    'keyctl', 'add_key', 'request_key', 'shmget', 'shmat', 'shmdt', 'shmctl',
                    'semget', 'semop', 'semtimedop', 'semctl', 'msgget', 'msgsnd', 'msgrcv', 'msgctl'):
        number = lib.seccomp_syscall_resolve_name(syscall.encode())
        if number >= 0 and lib.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0) != 0:
            raise RuntimeError(f'Cannot block syscall {syscall}')
    if lib.seccomp_load(ctx) != 0:
        raise RuntimeError('Cannot activate seccomp')
finally:
    lib.seccomp_release(ctx)

print('ARENA_SANDBOX_READY', flush=True)
sys.path.insert(0, '/bot')
runpy.run_path(sys.argv[1], run_name='__main__')
