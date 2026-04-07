#!/usr/bin/env python3
"""Unified local launcher for AcademeRAG backend + frontend."""

import argparse
import errno
import os
import signal
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parent
FRONTEND_DIR_CANDIDATES = (ROOT / 'Frontend', ROOT)
VENV_PYTHON_CANDIDATES = (
    ROOT / '.venv' / 'Scripts' / 'python.exe',
    ROOT / '.venv' / 'bin' / 'python',
)


def parse_args():
    parser = argparse.ArgumentParser(description='Run AcademeRAG services together.')
    parser.add_argument('--backend-host', default='127.0.0.1')
    parser.add_argument('--backend-port', type=int, default=8000)
    parser.add_argument('--frontend-host', default='127.0.0.1')
    parser.add_argument('--frontend-port', type=int, default=5173)
    parser.add_argument('--backend-only', action='store_true')
    parser.add_argument('--frontend-only', action='store_true')
    parser.add_argument('--skip-migrate', action='store_true')
    parser.add_argument('--no-health-wait', action='store_true')
    return parser.parse_args()


def can_bind_port(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True, None
        except OSError as exc:
            return False, exc


def resolve_start_port(host, preferred_port, service_name, max_tries=50, strict_permissions=True):
    for candidate_port in range(preferred_port, preferred_port + max_tries):
        can_bind, bind_error = can_bind_port(host, candidate_port)
        if can_bind:
            if candidate_port != preferred_port:
                print(
                    f'[setup] {service_name} port {host}:{preferred_port} unavailable; using {host}:{candidate_port}.'
                )
            return candidate_port

        if bind_error and bind_error.errno in (errno.EACCES, errno.EPERM):
            if strict_permissions:
                raise RuntimeError(
                    f'{service_name} cannot bind {host}:{candidate_port} due to permissions ({bind_error}).'
                ) from bind_error
            print(
                f'[warn] {service_name} port {host}:{candidate_port} is not permitted ({bind_error}); trying next port.'
            )
            continue

        if bind_error and bind_error.errno == errno.EADDRINUSE:
            continue

        if bind_error:
            print(
                f'[warn] {service_name} port check failed for {host}:{candidate_port} ({bind_error}); trying next port.'
            )

    raise RuntimeError(
        f'{service_name} could not find an available port near {host}:{preferred_port}.'
    )


def wait_for_http(url, timeout_s=30):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:  # nosec B310 - local dev URL
                if 200 <= resp.status < 500:
                    return True
        except (URLError, TimeoutError):
            time.sleep(0.5)
            continue
        time.sleep(0.5)
    return False


def resolve_frontend_dir():
    for candidate in FRONTEND_DIR_CANDIDATES:
        if (candidate / 'package.json').exists() and (candidate / 'vite.config.ts').exists():
            return candidate
    checked = ', '.join(str(path) for path in FRONTEND_DIR_CANDIDATES)
    raise RuntimeError(f'Unable to locate the frontend workspace. Checked: {checked}')


def is_runnable_executable(candidate):
    if not candidate:
        return False
    candidate_path = Path(candidate)
    if not candidate_path.exists():
        return False
    try:
        subprocess.run(
            [str(candidate_path), '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def resolve_python_bin():
    for candidate in VENV_PYTHON_CANDIDATES:
        if is_runnable_executable(candidate):
            return candidate
        if candidate.exists():
            print(f'[warn] Ignoring unusable virtualenv python at {candidate}.')

    current_python = Path(sys.executable)
    if is_runnable_executable(current_python):
        print('[warn] .venv python not found or unusable, using current python interpreter.')
        return current_python

    raise RuntimeError(
        'No usable Python interpreter found. Recreate the virtualenv or run the launcher with a working Python.'
    )


def ensure_django_available(python_bin):
    probe_cmd = [str(python_bin), '-c', 'import django; print(django.get_version())']
    try:
        result = subprocess.run(
            probe_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        version = result.stdout.strip()
        if version:
            print(f'[setup] Django runtime -> {python_bin} (django {version})')
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise RuntimeError(
            f'Python interpreter {python_bin} cannot import Django. Activate/install backend dependencies first. Details: {details}'
        ) from exc


def resolve_npm_command():
    npm_candidates = ['npm.cmd', 'npm.exe', 'npm'] if os.name == 'nt' else ['npm']
    for candidate in npm_candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return [resolved]
    raise RuntimeError('Node.js/npm was not found on PATH. Install Node.js 18+ and try again.')


def ensure_frontend_dependencies(frontend_dir, npm_cmd):
    vite_bin = frontend_dir / 'node_modules' / '.bin' / ('vite.cmd' if os.name == 'nt' else 'vite')
    if vite_bin.exists():
        return

    print('[setup] Frontend dependencies missing; running npm ci...')
    subprocess.run(npm_cmd + ['ci'], cwd=frontend_dir, check=True)


def stream_output(prefix, proc):
    for line in iter(proc.stdout.readline, ''):
        if not line:
            break
        print(f'[{prefix}] {line.rstrip()}')


def run_migrations(python_bin):
    cmd = [str(python_bin), 'manage.py', 'migrate']
    print('[setup] Running migrations...')
    subprocess.run(cmd, cwd=ROOT, check=True)


def start_backend(args, python_bin, port):
    cmd = [
        str(python_bin),
        'manage.py',
        'runserver',
        f'{args.backend_host}:{port}',
        '--noreload',
    ]
    env = os.environ.copy()
    env['PYTHONUNBUFFERED'] = '1'
    proc = subprocess.Popen(
        cmd,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=stream_output, args=('backend', proc), daemon=True).start()
    return proc


def start_frontend(args, frontend_dir, npm_cmd, port, backend_url=None):
    cmd = npm_cmd + [
        'run',
        'dev',
        '--',
        '--host',
        args.frontend_host,
        '--port',
        str(port),
    ]
    env = os.environ.copy()
    env['FORCE_COLOR'] = env.get('FORCE_COLOR', '1')
    if backend_url:
        env['VITE_API_BASE_URL'] = backend_url
        print(f'[setup] Frontend API target -> {backend_url}')
    proc = subprocess.Popen(
        cmd,
        cwd=frontend_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=stream_output, args=('frontend', proc), daemon=True).start()
    return proc


def shutdown_processes(processes):
    for proc in processes:
        if proc and proc.poll() is None:
            proc.terminate()
    for proc in processes:
        if proc and proc.poll() is None:
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()


def main():
    args = parse_args()
    processes = []
    backend_port = args.backend_port
    frontend_port = args.frontend_port

    if args.backend_only and args.frontend_only:
        print('Cannot use --backend-only and --frontend-only together.', file=sys.stderr)
        return 2

    python_bin = resolve_python_bin() if not args.frontend_only else None
    frontend_dir = resolve_frontend_dir() if not args.backend_only else None
    npm_cmd = resolve_npm_command() if frontend_dir else None

    if python_bin:
        ensure_django_available(python_bin)

    if not args.frontend_only and not args.skip_migrate:
        run_migrations(python_bin)

    def handle_signal(signum, _frame):
        print(f'\n[shutdown] Caught signal {signum}. Stopping services...')
        shutdown_processes(processes)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        if not args.frontend_only:
            backend_port = resolve_start_port(args.backend_host, args.backend_port, 'Backend')
            processes.append(start_backend(args, python_bin, backend_port))
        if not args.backend_only:
            if args.frontend_host == args.backend_host and frontend_port == backend_port:
                frontend_port += 1
            frontend_port = resolve_start_port(
                args.frontend_host,
                frontend_port,
                'Frontend',
                strict_permissions=False,
            )
            ensure_frontend_dependencies(frontend_dir, npm_cmd)
            resolved_backend_url = None
            if not args.frontend_only:
                resolved_backend_url = f'http://{args.backend_host}:{backend_port}'
            processes.append(
                start_frontend(
                    args,
                    frontend_dir,
                    npm_cmd,
                    frontend_port,
                    backend_url=resolved_backend_url,
                )
            )
    except Exception as exc:
        print(f'[error] {exc}', file=sys.stderr)
        shutdown_processes(processes)
        return 1

    if not args.no_health_wait:
        if not args.frontend_only:
            backend_url = f'http://{args.backend_host}:{backend_port}/api/health/'
            ok = wait_for_http(backend_url)
            print(f"[ready] backend: {'ok' if ok else 'not-ready'} -> {backend_url}")
        if not args.backend_only:
            frontend_url = f'http://{args.frontend_host}:{frontend_port}'
            ok = wait_for_http(frontend_url)
            print(f"[ready] frontend: {'ok' if ok else 'not-ready'} -> {frontend_url}")

    print('[run] Services started. Press Ctrl+C to stop.')

    try:
        while True:
            for proc in processes:
                code = proc.poll()
                if code is not None:
                    print(f'[error] A service exited with code {code}. Shutting down...')
                    shutdown_processes(processes)
                    return code
            time.sleep(0.5)
    except KeyboardInterrupt:
        shutdown_processes(processes)
        return 0


if __name__ == '__main__':
    raise SystemExit(main())