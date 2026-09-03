#!/usr/bin/env python3
"""Serve the simulator on your classroom network (Version A).

    python serve.py

Learners on the same network open the URL printed below (or a session link an
instructor hands them). Chat, mail, tickets, scenarios and grading run here on
the server; learners write code on their own machines and submit a patch via the
Submit app.

Config comes from environment variables, same as running uvicorn directly:
  LLM_PROVIDER, OLLAMA_MODEL, ANTHROPIC_MODEL/ANTHROPIC_API_KEY, ENV_PROVIDER,
  INSTRUCTOR_PASSWORD, PORT (default 8000).
"""
import os
import socket


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))          # no packets sent; just picks the route
        ips.add(s.getsockname()[0]); s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


def main():
    port = int(os.environ.get("PORT", "8000"))
    provider = os.environ.get("LLM_PROVIDER", "fake")
    ips = lan_ips() or ["<this-machine-ip>"]

    print("\n" + "=" * 60)
    print("  Engineering Flight Simulator — classroom server")
    print("=" * 60)
    print(f"  Model provider : {provider}"
          + ("   (set LLM_PROVIDER=ollama|anthropic for real sessions)"
             if provider == "fake" else ""))
    print("  Learners open  :")
    for ip in ips:
        print(f"                   http://{ip}:{port}")
    print("  Instructor     :")
    for ip in ips:
        print(f"                   http://{ip}:{port}/instructor")
    if not os.environ.get("INSTRUCTOR_PASSWORD"):
        print("\n  ! The instructor password is the default and travels in the clear")
        print("    over your network. Set INSTRUCTOR_PASSWORD to something private,")
        print("    and only open /instructor from the teacher's machine.")
    print("=" * 60 + "\n")

    import uvicorn
    uvicorn.run("sim.app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
