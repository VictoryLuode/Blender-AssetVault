#!/usr/bin/env bash
# verify.sh — 一条命令回答「这个仓现在可发布吗？」
#
#   ./verify.sh           全量：版本一致 + 语法 + 端到端测试 + 打包依赖
#   ./verify.sh --quick   快速：只做版本一致 + 语法（改文档、小改时用）
#
# 退出码：0 = 全绿可发布；1 = 有失败。
#
# 三条纪律（动这个文件之前先读）：
#   1. 每个 gate 都必须真的能变红。永远绿的 gate 比没有 gate 更糟——它是对
#      坏代码的 ✓ 背书。加 gate 时故意弄坏一次，确认它红了，再改回来。
#   2. 本脚本是验证的唯一入口：本地跑它、发版前跑它、将来 CI 也只调它。
#   3. 版本号的唯一真源是 git tag；文件里的字面量是它的投影，两者必须相等。
#
# 本仓版本的三个落点（三处必须相等）：
#   asset_vault/__init__.py  ->  __version__
#   asset_vault/__init__.py  ->  bl_info["version"]  （必须是字面量，见下）
#   CHANGELOG.md             ->  顶部 "## vX.Y.Z"
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

QUICK=0
for a in "$@"; do
  case "$a" in
    --quick) QUICK=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done

failed=0
step() { printf '\n== %s\n' "$1"; }
pass() { printf '   ok   %s\n' "$1"; }
fail() { printf '   FAIL %s\n' "$1"; failed=1; }

PY="$(command -v python || command -v python3 || true)"
ADDON="asset_vault/__init__.py"

# --------------------------------------------------------- 1. 版本一致性
step "1. version consistency"

code_version=""
lit_version=""
if [ -z "$PY" ]; then
  fail "no python on PATH — cannot check versions"
else
  report="$("$PY" - "$ADDON" <<'PYEOF' 2>&1
import ast, pathlib, sys
path = pathlib.Path(sys.argv[1])
code, lit, err = "", "", ""
for node in ast.parse(path.read_text(encoding="utf-8")).body:
    if not isinstance(node, ast.Assign):
        continue
    names = [getattr(t, "id", "") for t in node.targets]
    if "__version__" in names:
        try:
            v = ast.literal_eval(node.value)
            code = v if isinstance(v, str) else ""
        except ValueError:
            err = "version-not-literal"
    if "bl_info" in names:
        try:
            info = ast.literal_eval(node.value)
        except ValueError:
            err = err or "bl_info-not-a-literal"
            continue
        v = info.get("version")
        lit = ".".join(str(x) for x in v) if isinstance(v, (tuple, list)) else ""
print("|".join((code, lit, err)))
PYEOF
)"
  code_version="${report%%|*}"
  rest="${report#*|}"; lit_version="${rest%%|*}"; verr="${rest#*|}"

  case "$verr" in
    bl_info-not-a-literal)
      fail "bl_info is NOT a literal — Blender reads it with ast.literal_eval;"
      fail "  a computed value makes the add-on invisible in Preferences" ;;
    version-not-literal) fail "__version__ must be a plain string literal" ;;
  esac

  [ -n "$code_version" ] && pass "__version__ = $code_version" \
    || fail "no string __version__ in $ADDON"
  [ -n "$lit_version" ] && pass "bl_info version = $lit_version  (literal, Blender-readable)" \
    || fail "no literal bl_info[\"version\"] tuple in $ADDON"

  if [ -n "$code_version" ] && [ -n "$lit_version" ] && [ "$code_version" != "$lit_version" ]; then
    fail "__version__ ($code_version) and bl_info ($lit_version) disagree"
  fi
fi

changelog_version="$(grep -m1 -E '^## +v?[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md 2>/dev/null \
  | sed -E 's/^## +v?([0-9]+\.[0-9]+\.[0-9]+).*/\1/')"
if [ -n "$code_version" ] && [ "$code_version" = "$changelog_version" ]; then
  pass "CHANGELOG.md top heading agrees ($changelog_version)"
else
  fail "version mismatch: code=${code_version:-?}  CHANGELOG=${changelog_version:-none}"
fi

tags_here="$(git tag --points-at HEAD 2>/dev/null || true)"
if [ -z "$tags_here" ]; then
  pass "HEAD carries no tag (fine — this is the pre-release state)"
else
  for t in $tags_here; do
    if [ "$(git cat-file -t "$t" 2>/dev/null)" = "tag" ]; then
      pass "tag $t is annotated"
    else
      fail "tag $t is lightweight — git describe ignores those; re-tag with: git tag -a"
    fi
  done
fi

# --------------------------------------------------------- 2. 语法
step "2. syntax"
if [ -z "$PY" ]; then
  fail "no python on PATH — cannot check syntax"
else
  syntax_report="$("$PY" - <<'PYEOF' 2>&1
import ast, pathlib
bad = []
for p in sorted(pathlib.Path("asset_vault").rglob("*.py")):
    try:
        ast.parse(p.read_text(encoding="utf-8"), str(p))
    except SyntaxError as e:
        bad.append(f"{p}:{e.lineno}: {e.msg}")
print("\n".join(bad))
PYEOF
)"
  [ -z "$syntax_report" ] && pass "all .py under asset_vault/ parse" || fail "$syntax_report"
fi

# --------------------------------------------------------- 3. 端到端测试
if [ "$QUICK" -eq 1 ]; then
  step "3. tests  (skipped: --quick)"
else
  step "3. tests"
  echo
  if "$REPO/tests/run_tests.sh"; then
    pass "tests/run_tests.sh green"
  else
    fail "tests/run_tests.sh reported failures (see output above)"
  fi
fi

# --------------------------------------------------------- 4. 安装脚本
step "4. installers"
if bash -n install.sh 2>/dev/null; then
  pass "install.sh parses"
else
  fail "install.sh has a syntax error"
fi

# 两扇门（bash 的 install.sh、Windows 的 install.ps1）必须落到完全相同的文件：
# 各装进一棵临时树，再和 asset_vault/ 逐文件比。PS 只在一部分机器上有——
# 没有时明确 skip，不假装比过。
if [ ! -f install.ps1 ]; then
  fail "install.ps1 is missing — Windows users have PowerShell, not bash"
else
  PS="$(command -v powershell.exe || command -v pwsh || true)"
  if [ -z "$PS" ]; then
    echo "   note: no PowerShell on this machine — install.ps1 not exercised (Windows-only door)"
  else
    STAGE="$(mktemp -d "${TMPDIR:-/tmp}/avinstall.XXXXXX" 2>/dev/null || true)"
    if [ -z "$STAGE" ] || [ ! -d "$STAGE" ]; then
      fail "installer smoke test: cannot create a scratch tree"
    else
      mkdir -p "$STAGE/bash/addons" "$STAGE/ps/addons"
      bash_door=0; ps_door=0
      ./install.sh "$STAGE/bash/addons" >/dev/null 2>&1 && bash_door=1
      ps_win="$(cygpath -w "$STAGE/ps/addons" 2>/dev/null || printf '%s' "$STAGE/ps/addons")"
      script_win="$(cygpath -w "$REPO/install.ps1" 2>/dev/null || printf '%s' "$REPO/install.ps1")"
      "$PS" -NoProfile -ExecutionPolicy Bypass -File "$script_win" -BlenderAddons "$ps_win" >/dev/null 2>&1 && ps_door=1
      if [ "$bash_door" -eq 1 ] && [ "$ps_door" -eq 1 ]; then
        pass "both doors installed into a throwaway tree"
        drift="$(diff -r --exclude=__pycache__ asset_vault "$STAGE/bash/addons/asset_vault" 2>&1
                 diff -r --exclude=__pycache__ asset_vault "$STAGE/ps/addons/asset_vault" 2>&1)"
        if [ -z "$drift" ]; then
          pass "both doors landed byte-identical to asset_vault/"
        else
          fail "an installer drifted from asset_vault/:"
          printf '%s\n' "$drift" | head -5
        fi
        if [ -n "$(find "$STAGE" -name __pycache__ -print -quit)" ]; then
          fail "an installer left __pycache__ inside the add-on folder"
        else
          pass "no __pycache__ in the installed folder"
        fi
      else
        fail "installer smoke test did not run (bash door=$bash_door, PowerShell door=$ps_door)"
      fi
      rm -rf "$STAGE"
    fi
  fi
fi

# --------------------------------------------------------- 汇总
echo
if [ "$failed" -eq 0 ]; then
  echo "VERIFY PASSED — this tree is releasable"
else
  echo "VERIFY FAILED"
fi
exit "$failed"
