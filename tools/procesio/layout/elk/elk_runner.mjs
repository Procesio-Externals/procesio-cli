// Synchronous-from-the-caller's-view elkjs runner for the ELK 'layered' layout engine.
//
// Contract: reads ONE ELK graph JSON object on stdin (the shape elkjs expects:
// {id, layoutOptions, children:[...], edges:[...]} with nested children for compound
// nodes), runs elk.layout(), and writes the laid-out graph JSON to stdout. Node/edge
// coordinates in the output are ELK's: x/y are the TOP-LEFT of each node RELATIVE to its
// parent; compound nodes carry their computed width/height. On any failure it prints a
// single-line {"error": "..."} JSON to stdout and exits non-zero (stderr carries detail).
//
// This is invoked by ../elk_engine.py via `node elk_runner.mjs`. It performs no network
// I/O — elkjs is a local dependency. Keep it dependency-light and side-effect-free.

import ELK from 'elkjs';

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => { buf += c; });
    process.stdin.on('end', () => resolve(buf));
    process.stdin.on('error', reject);
  });
}

async function main() {
  const raw = await readStdin();
  let graph;
  try {
    graph = JSON.parse(raw);
  } catch (e) {
    process.stdout.write(JSON.stringify({ error: `invalid graph JSON: ${e.message}` }));
    process.exit(2);
    return;
  }
  const elk = new ELK();
  try {
    const laid = await elk.layout(graph);
    process.stdout.write(JSON.stringify(laid));
  } catch (e) {
    process.stderr.write(String((e && e.stack) || e) + '\n');
    process.stdout.write(JSON.stringify({ error: `elk.layout failed: ${e && e.message ? e.message : e}` }));
    process.exit(1);
  }
}

main().catch((e) => {
  process.stderr.write(String((e && e.stack) || e) + '\n');
  process.stdout.write(JSON.stringify({ error: `runner crashed: ${e && e.message ? e.message : e}` }));
  process.exit(1);
});
