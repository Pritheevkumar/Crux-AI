import yaml
import commands
cfg = yaml.safe_load(open("config.yaml","r",encoding="utf-8"))

tests = [
    "open notepad",
    "search hello world",
    "volume up",
    "brightness down", # WARNING: will only work if allowed in config
    "play music",
    "crux write a python program for bubble sort",
]

for t in tests:
    handled, resp = commands.handle_command(t, cfg)
    print(f"[{t}] -> handled={handled} resp={resp[:120]}")
