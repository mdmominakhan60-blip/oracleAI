#!/usr/bin/env python3
"""TCP bridge docker0(172.17.0.1):20128 -> loopback 127.0.0.1:20128 (ssh tunnel).

BUS-704: контейнеры oracle_internal достигают ПК-omniroute через reverse-tunnel
(см. infra/systemd/oracleai-llm-bridge.service). Без внешних зависимостей."""
import socket, threading, sys

LISTEN = ("172.17.0.1", 20128)
UPSTREAM = ("127.0.0.1", 20128)

def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try: s.shutdown(socket.SHUT_RDWR)
            except OSError: pass

def handle(client):
    try:
        upstream = socket.create_connection(UPSTREAM, timeout=10)
    except OSError as e:
        print(f"upstream connect failed: {e}", file=sys.stderr, flush=True)
        client.close()
        return
    t = threading.Thread(target=pipe, args=(client, upstream), daemon=True)
    t.start()
    pipe(upstream, client)
    client.close()
    upstream.close()

def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(128)
    print(f"bridge {LISTEN} -> {UPSTREAM}", flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()

if __name__ == "__main__":
    main()
