import asyncio
import os
import sys
import signal
import json
from datetime import datetime, timezone
from uuid import uuid4
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich import box
from orchestrator.conductor import Conductor
from shared.agent_timeline import HumanInputPolicy

load_dotenv()
console = Console()
conductor = Conductor(tick_interval_ms=10.0)

AGENT_COLORS = {
    "planner": "bold cyan", "blender": "bold green", "unity": "bold bright_cyan",
    "godot": "bold bright_green", "memory": "bold magenta",
    "tool": "bold yellow", "review": "bold red", "fallback": "bold white",
    "human": "bold blue", "world": "bold white",
}


class ShutdownManager:
    def __init__(self):
        self.shutdown_event = asyncio.Event()

    async def wait_for_shutdown(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._trigger)
        await self.shutdown_event.wait()

    def _trigger(self):
        console.print("\n[yellow]⏳ Stänger ner agenternas värld...[/]")
        self.shutdown_event.set()


async def cleanup():
    console.print("[dim]Closing Supabase client...[/]")
    try:
        await conductor.db.supabase.postgrest.aclose()
    except Exception:
        pass
    console.print("[dim]Telemetry:[/]")
    try:
        from shared.telemetry import telemetry
        recent = telemetry.get_recent(10)
        if recent:
            for s in recent:
                status = "✅" if s.success else "❌"
                lat = f"{s.latency_ms:.0f}ms" if s.latency_ms else "?"
                console.print(f"  {status} [{s.agent_id}] {s.operation} ({lat})")
    except Exception:
        pass


async def chat_loop():
    shutdown = ShutdownManager()

    console.print(
        Panel.fit(
            "[bold cyan]Agenternas värld[/bold cyan]\n"
            "Agenterna tickar oavsett om du tittar.\n"
            "Skriv en uppgift, eller använd kommandon:\n"
            "/status, /pause, /resume, /detail, /help, /quit",
            border_style="cyan",
        )
    )

    conductor_task = asyncio.create_task(conductor.run(), name="conductor")
    shutdown_task = asyncio.create_task(shutdown.wait_for_shutdown(), name="shutdown_watch")

    async def read_input():
        while not shutdown.shutdown_event.is_set():
            line = await asyncio.to_thread(input, "\n[You] ")
            cmd = line.strip()

            if cmd.lower() in ("/quit", "/exit"):
                shutdown._trigger()
                break

            if cmd.lower() == "/help":
                p = (
                    "[bold]Kommandon:[/]\n"                "  /status   — Visa vad agenterna gjort sen du tittade\n"
                "  /detail   — Detaljerad vy av senaste händelser\n"
                "  /pause    — Frys agenternas tidslinje\n"
                "  /resume   — Återuppta agenternas tidslinje\n"
                "  /guest <handle> <text>  — G\u00e4st-publikation p\u00e5 bussen (Charter 5.4)\n"
                "  /unguest <handle>     — Avsluta g\u00e4st-session (Charter 5.4)\n"
                "  /help     — Visa detta\n"
                "  /quit     — Stäng ner agenternas värld"
                )
                console.print(Panel(p, title="Help", border_style="dim"))

            elif cmd.lower() == "/status":
                view = conductor.human_view()
                console.print(Panel(
                    Markdown(view),
                    title="🕐 Agenternas värld",
                    border_style="green",
                ))

            elif cmd.lower() == "/detail":
                detail = conductor.human_detail()
                console.print(Panel(
                    detail,
                    title="🔍 Detaljer",
                    border_style="blue",
                ))

            elif cmd.lower() == "/pause":
                conductor.pause()
                console.print("[yellow]⏸️ Världen pausad. Agenterna fryser efter nästa operation.[/]")

            elif cmd.lower() == "/resume":
                conductor.resume()
                console.print("[green]▶️ Världen återupptagen. Agenterna tickar igen.[/]")

            elif cmd.lower().startswith("/guest"):
                # Charter Article 5.4: humans are peers, not controllers.
                # Routes a human message into the HumanGuestAgent peer seat.
                parts = cmd.split(maxsplit=2)
                if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
                    console.print("[red]/guest kräver: /guest <handle> <text>[/]")
                else:
                    handle, text = parts[1].strip(), parts[2].strip()
                    try:
                        msg_id = await conductor.publish_as_guest(handle, text)
                    except ValueError as e:
                        console.print(f"[red]{e}[/]")
                        continue
                    console.print(f"[bold blue]👤 Guest {handle}:[/] {text[:80]}{'...' if len(text) > 80 else ''} (id={msg_id.message_id if msg_id else '??'})")

            elif cmd.lower().startswith("/unguest"):
                parts = cmd.split(maxsplit=1)
                if len(parts) < 2 or not parts[1].strip():
                    console.print("[red]/unguest kräver: /unguest <handle>[/]")
                else:
                    handle = parts[1].strip()
                    try:
                        removed = await conductor.remove_guest(handle)
                    except ValueError as e:
                        console.print(f"[red]{e}[/]")
                        continue
                    if removed:
                        console.print(f"[dim]Guest {handle} removed from bus.[/]")
                    else:
                        console.print(f"[dim]Guest {handle} was not on the bus.[/]")

            elif cmd.strip():
                if conductor.world.timeline._paused:
                    conductor.resume()
                goal = conductor.add_goal(line)
                console.print(
                    f"[dim]🎯 Mål lagt till: {line[:60]}{'...' if len(line) > 60 else ''}[/]"
                )

    input_task = asyncio.create_task(read_input(), name="input_reader")

    await shutdown.shutdown_event.wait()

    conductor.stop()
    await cleanup()

    for task in (conductor_task, input_task, shutdown_task):
        task.cancel()
    await asyncio.gather(
        *[t for t in (conductor_task, input_task, shutdown_task) if not t.done()],
        return_exceptions=True,
    )

    console.print("[green]✓ Agenternas värld har stannat[/]")
    sys.exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(chat_loop())
    except KeyboardInterrupt:
        pass
