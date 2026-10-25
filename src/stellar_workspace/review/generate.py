"""Self-contained review UI; layout/styles adapted from Apache-2.0 pyre-review."""
import json
from importlib.resources import files
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename, TextLexer
from pygments.util import ClassNotFound


def generate_html(diffs, records, topic, base, commits, context, *, token=None):
    formatter = HtmlFormatter(nowrap=True, classprefix="hl-")
    file_data = []
    for diff in diffs:
        try:
            lexer = get_lexer_for_filename(diff.path, stripnl=False, ensurenl=False)
        except ClassNotFound:
            lexer = TextLexer(stripnl=False, ensurenl=False)
        rendered = []
        for line in diff.lines:
            rendered.append({"type": line.type, "old": line.old_lineno, "new": line.new_lineno,
                             "html": highlight(line.content, lexer, formatter).rstrip("\n"),
                             "no_newline": line.no_newline})
        file_data.append({"path": diff.path, "old_path": diff.old_path, "status": diff.status,
                          "additions": diff.additions, "deletions": diff.deletions, "binary": diff.binary,
                          "metadata": diff.metadata, "lines": rendered})
    data = {"topic": topic, "base": base, "context": context, "commits": commits,
            "files": file_data, "records": records, "token": token}
    encoded = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    resource = files("stellar_workspace").joinpath("resources")
    return resource.joinpath("review.html").read_text().replace("/* __PYGMENTS_CSS__ */", formatter.get_style_defs()) + '\n<script>\nconst DATA = ' + encoded + ';\n' + SCRIPT + '\n</script>\n</body>\n</html>\n'


SCRIPT = r'''
let currentFileIdx = -1, currentVerdictType = null;
function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function button(text, fn) {
  const node = element('button', text, 'btn');
  node.disabled = !DATA.token;
  node.addEventListener('click', fn);
  return node;
}
function toast(text) {
  const node = document.getElementById('toast');
  node.textContent = text; node.classList.add('show');
  setTimeout(() => node.classList.remove('show'), 4000);
}
async function api(path, body) {
  const response = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json', 'X-SW-Token':DATA.token}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || response.statusText);
  const fresh = await fetch('/api/comments');
  if (!fresh.ok) throw Error('Cannot refresh review records');
  DATA.records = await fresh.json();
  buildFileTree(); selectFile(currentFileIdx, true);
  return result;
}
function buildFileTree() {
  const tree = document.getElementById('file-tree'); tree.replaceChildren();
  DATA.files.forEach((file, index) => {
    const item = element('div', `${file.status} ${file.path}`, 'tree-item');
    if (DATA.records.some(c => c.type === 'comment' && c.file === file.path && !c.resolved)) item.append(' ●');
    item.onclick = () => selectFile(index);
    tree.append(item);
  });
}
function selectFile(index, preserve=false) {
  if (index < 0 || index >= DATA.files.length) return;
  currentFileIdx = index;
  const file = DATA.files[index], view = document.getElementById('file-view'), scroll = view.scrollTop;
  view.replaceChildren(element('div', `${file.status} ${file.old_path ? file.old_path+' → ' : ''}${file.path}  +${file.additions} -${file.deletions}`, 'file-header'));
  if (file.binary || file.metadata) view.append(element('pre', file.metadata || 'Binary file changed'));
  const table = element('table', undefined, 'code');
  const remaining = new Set(DATA.records.filter(c => c.type === 'comment' && c.file === file.path).map(c => c.id));
  file.lines.forEach(line => {
    const row = element('tr', undefined, line.type === 'added' ? 'line-added' : line.type === 'deleted' ? 'line-deleted' : '');
    const old = element('td', line.old ?? '', 'ln ln-old'), next = element('td', line.new ?? '', 'ln ln-new');
    if (DATA.token && line.old) old.onclick = () => addComment(file.path, line.old, 'left');
    if (DATA.token && line.new) next.onclick = () => addComment(file.path, line.new, 'right');
    const code = element('td', undefined, 'code-content');
    code.innerHTML = line.html; // only Pygments-escaped source, never comments/paths
    if (line.no_newline) code.append(element('span', ' ⏎ no final newline'));
    row.append(old, next, code); table.append(row);
    DATA.records.filter(c => remaining.has(c.id) && c.line === (c.side === 'left' ? line.old : line.new)).forEach(c => {
      table.append(commentRow(c)); remaining.delete(c.id);
    });
  });
  DATA.records.filter(c => remaining.has(c.id)).forEach(c => table.append(commentRow(c)));
  view.append(table);
  const verdicts = DATA.records.filter(c => c.type === 'verdict');
  for (const verdict of verdicts) view.append(element('p', `${verdict.author}: ${verdict.verdict} — ${verdict.body}${contextLabel(verdict)}`));
  view.scrollTop = preserve ? scroll : 0;
}
function contextLabel(record) {
  if (!record.context) return ' [comparison unspecified]';
  return record.context.base !== DATA.context.base || record.context.mode !== DATA.context.mode ? ` [different comparison: ${record.context.base.slice(0,12)}, ${record.context.mode}]` : '';
}
function commentRow(comment) {
  const row = element('tr', undefined, 'comment-row'), cell = element('td'); cell.colSpan=3;
  const block = element('div', undefined, 'comment-block');
  block.append(element('div', `${comment.author} · ${comment.timestamp} · ${comment.side}:${comment.line}${contextLabel(comment)}`, 'comment-header'));
  block.append(element('div', comment.body, 'comment-body'));
  block.append(button(comment.resolved ? 'Unresolve' : 'Resolve', async () => {
    try { await api(comment.resolved ? '/api/unresolve' : '/api/resolve', {id:comment.id}); }
    catch (error) { toast(error.message); }
  }));
  if (comment.resolved) block.append(' ✓ resolved');
  cell.append(block); row.append(cell); return row;
}
async function addComment(file, line, side) {
  if (!DATA.token) return;
  const body = prompt(`Comment on ${file}:${line} (${side})`);
  if (!body || !body.trim()) return;
  try { await api('/api/comment', {file, line, side, body}); toast('Comment saved'); }
  catch (error) { toast(error.message); }
}
function showVerdict(type) {
  if (!DATA.token) return;
  currentVerdictType = type;
  document.getElementById('overlay').style.display = 'block';
  document.getElementById('verdict-dialog').style.display = 'block';
  document.getElementById('verdict-title').textContent = type;
  document.getElementById('verdict-body').focus();
}
function hideVerdict() {
  document.getElementById('overlay').style.display = 'none';
  document.getElementById('verdict-dialog').style.display = 'none';
}
async function submitVerdict() {
  try {
    await api('/api/verdict', {verdict:currentVerdictType, body:document.getElementById('verdict-body').value});
    hideVerdict(); toast('Verdict saved');
  } catch (error) { toast(error.message); }
}
function navigate(selector, direction) {
  const nodes = Array.from(document.querySelectorAll(selector)), view = document.getElementById('file-view');
  const edge = view.getBoundingClientRect().top + 12;
  const ordered = direction > 0 ? nodes : nodes.reverse();
  const target = ordered.find(node => direction > 0 ? node.getBoundingClientRect().top > edge : node.getBoundingClientRect().top < edge - 2);
  if (target) target.scrollIntoView({block:'start'});
}
function init() {
  document.getElementById('review-title').textContent = `Review: ${DATA.topic} → ${DATA.base}`;
  document.getElementById('review-stats').textContent = `${DATA.context.mode}; commit ${DATA.context.commit.slice(0,12)}; base ${DATA.context.base.slice(0,12)}${DATA.token ? '' : ' — READ-ONLY SNAPSHOT'}`;
  if (!DATA.token) document.querySelectorAll('.actions button, #verdict-submit-btn').forEach(b => b.disabled=true);
  buildFileTree(); selectFile(0);
  document.addEventListener('keydown', event => {
    if (['INPUT','TEXTAREA'].includes(event.target.tagName)) return;
    const key=event.key;
    if (key==='j') selectFile(currentFileIdx+1);
    if (key==='k') selectFile(currentFileIdx-1);
    if (key==='n' || key==='N') navigate('.comment-row', key==='n' ? 1 : -1);
    if (key===']' || key==='[') navigate('.line-added,.line-deleted', key===']' ? 1 : -1);
    if (key==='Escape') hideVerdict();
  });
}
init();
'''
