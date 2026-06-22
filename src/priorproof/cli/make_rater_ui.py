from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

from priorproof.data.io import read_json
from priorproof.evaluation.packets import require_complete_narratives


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a static blinded rater UI for a study packet.")
    parser.add_argument("--packet", required=True, help="study_packet.json from priorproof-study-packet.")
    parser.add_argument("--out", required=True, help="Output HTML path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    packet = read_json(args.packet)
    if not isinstance(packet, dict) or not isinstance(packet.get("pairs"), list):
        raise ValueError("--packet must contain an object with a `pairs` list")
    require_complete_narratives(packet, context="priorproof-rater-ui")
    payload = json.dumps(packet).replace("</", "<\\/")
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(payload), encoding="utf-8")


def render_html(payload: str) -> str:
    title = html.escape("PriorProof Rater Packet")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #202124;
      --muted: #60646c;
      --line: #d9d9d2;
      --accent: #0f766e;
      --accent-2: #334155;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 5;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 12px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(247, 247, 244, 0.96);
    }}
    h1 {{ margin: 0; font-size: 18px; font-weight: 650; }}
    .toolbar {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    button {{
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      color: var(--ink);
      padding: 8px 10px;
      font: inherit;
      cursor: pointer;
    }}
    button.primary {{ background: var(--accent); border-color: var(--accent); color: white; }}
    button.choice {{
      width: 100%;
      min-height: 42px;
      font-weight: 650;
    }}
    button.choice.selected {{ background: var(--accent-2); border-color: var(--accent-2); color: white; }}
    main {{ padding: 16px; max-width: 1600px; margin: 0 auto; }}
    .meta {{ color: var(--muted); font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; }}
    .side {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
      overflow: hidden;
    }}
    .side-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
    }}
    .side-title {{ min-width: 0; font-weight: 650; overflow-wrap: anywhere; }}
    .content {{ padding: 12px; display: grid; gap: 12px; }}
    .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0; }}
    pre {{
      margin: 0;
      padding: 10px;
      overflow: auto;
      max-height: 340px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fbfbf9;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      white-space: pre-wrap;
    }}
    .statement, .argument {{ line-height: 1.45; overflow-wrap: anywhere; }}
    .nav {{ display: flex; gap: 8px; align-items: center; }}
    .status {{ min-width: 110px; text-align: center; }}
    @media (max-width: 900px) {{
      header {{ align-items: flex-start; flex-direction: column; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <script id="packet" type="application/json">{payload}</script>
  <header>
    <div>
      <h1>PriorProof Rater Packet</h1>
      <div class="meta" id="packetMeta"></div>
    </div>
    <div class="toolbar">
      <button id="prev">Prev</button>
      <span class="status" id="status"></span>
      <button id="next">Next</button>
      <button id="download" class="primary">Download responses</button>
    </div>
  </header>
  <main>
    <p class="meta" id="prompt"></p>
    <div class="grid">
      <section class="side">
        <div class="side-header">
          <div class="side-title" id="leftName"></div>
          <button class="choice" id="chooseLeft">Choose left</button>
        </div>
        <div class="content" id="leftContent"></div>
      </section>
      <section class="side">
        <div class="side-header">
          <div class="side-title" id="rightName"></div>
          <button class="choice" id="chooseRight">Choose right</button>
        </div>
        <div class="content" id="rightContent"></div>
      </section>
    </div>
  </main>
  <script>
    const packet = JSON.parse(document.getElementById('packet').textContent);
    const storageKey = 'priorproof-rater-' + packet.name;
    let idx = 0;
    let responses = JSON.parse(localStorage.getItem(storageKey) || '{{}}');
    const esc = (s) => String(s || '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}}[c]));
    function sideHtml(side) {{
      const source = side.lean_source || side.statement || '';
      return `
        <div><div class="label">Statement</div><div class="statement">${{esc(side.statement)}}</div></div>
        <div><div class="label">Proof narrative</div><div class="argument">${{esc(side.human_argument)}}</div></div>
        <div><div class="label">Proof source</div><pre>${{esc(source)}}</pre></div>
      `;
    }}
    function render() {{
      const pair = packet.pairs[idx];
      document.getElementById('packetMeta').textContent = `${{packet.pair_count}} pairs`;
      document.getElementById('status').textContent = `${{idx + 1}} / ${{packet.pairs.length}}`;
      document.getElementById('prompt').textContent = pair.prompt;
      document.getElementById('leftName').textContent = pair.left.name;
      document.getElementById('rightName').textContent = pair.right.name;
      document.getElementById('leftContent').innerHTML = sideHtml(pair.left);
      document.getElementById('rightContent').innerHTML = sideHtml(pair.right);
      const choice = responses[pair.pair_id]?.choice;
      document.getElementById('chooseLeft').classList.toggle('selected', choice === 'left');
      document.getElementById('chooseRight').classList.toggle('selected', choice === 'right');
    }}
    function choose(choice) {{
      const pair = packet.pairs[idx];
      responses[pair.pair_id] = {{
        pair_id: pair.pair_id,
        choice,
        left: pair.left.name,
        right: pair.right.name,
        recorded_at: new Date().toISOString()
      }};
      localStorage.setItem(storageKey, JSON.stringify(responses));
      render();
    }}
    document.getElementById('chooseLeft').onclick = () => choose('left');
    document.getElementById('chooseRight').onclick = () => choose('right');
    document.getElementById('prev').onclick = () => {{ idx = Math.max(0, idx - 1); render(); }};
    document.getElementById('next').onclick = () => {{ idx = Math.min(packet.pairs.length - 1, idx + 1); render(); }};
    document.getElementById('download').onclick = () => {{
      const rows = Object.values(responses).map(row => JSON.stringify(row)).join('\\n') + '\\n';
      const blob = new Blob([rows], {{type: 'application/jsonl'}});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'priorproof_rater_responses.jsonl';
      a.click();
      URL.revokeObjectURL(url);
    }};
    render();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
