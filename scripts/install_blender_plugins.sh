#!/usr/bin/env bash
# Install Blender plugins for the agent ecosystem.
#
# Usage:
#   chmod +x scripts/install_blender_plugins.sh
#   ./scripts/install_blender_plugins.sh           # auto-detect Blender version
#   BLENDER_VERSION=4.3 ./scripts/install_blender_plugins.sh
#
# Detects Blender addons directory and installs community plugins
# via git clone / pip / direct download. Bundled plugins are just enabled.

set -euo pipefail

# ─── Config ──────────────────────────────────────────────────────────
BLENDER_VERSION="${BLENDER_VERSION:-}"
PLUGIN_DIR=""

# ─── Detect Blender ─────────────────────────────────────────────────
detect_blender() {
    BLENDER_BIN=""
    BLENDER_BIN=$(command -v blender 2>/dev/null || true)
    if [[ -z "$BLENDER_BIN" ]]; then
        BLENDER_BIN=$(mdfind "kMDItemKind == 'Application' && kMDItemFSName == 'Blender*'" 2>/dev/null | head -1)
        if [[ -n "$BLENDER_BIN" ]]; then
            BLENDER_BIN="$BLENDER_BIN/Contents/MacOS/blender"
        fi
    fi

    if [[ -z "$BLENDER_BIN" || ! -x "$BLENDER_BIN" ]]; then
        echo "❌ Blender not found. Install Blender first: https://www.blender.org/download/"
        echo "   Or set BLENDER_PATH env var."
        exit 1
    fi

    echo "✓ Found Blender: $BLENDER_BIN"

    if [[ -z "$BLENDER_VERSION" ]]; then
        BLENDER_VERSION=$("$BLENDER_BIN" --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "4.2")
    fi
    echo "  Version: $BLENDER_VERSION"

    if [[ "$(uname)" == "Darwin" ]]; then
        PLUGIN_DIR="$HOME/Library/Application Support/Blender/${BLENDER_VERSION}/scripts/addons"
    elif [[ "$(uname)" == "Linux" ]]; then
        PLUGIN_DIR="$HOME/.config/blender/${BLENDER_VERSION}/scripts/addons"
    else
        PLUGIN_DIR="$APPDATA/Blender Foundation/Blender/${BLENDER_VERSION}/scripts/addons"
    fi

    mkdir -p "$PLUGIN_DIR"
    echo "  Plugins dir: $PLUGIN_DIR"
}

# ─── Plugin sources ──────────────────────────────────────────────────

# ─── Blender Extensions CLI (Blender 4.2+) ─────────────────────────
install_extension() {
    local ext_id="$1"
    echo ""
    echo "  → $ext_id (via Blender Extensions)"
    "$BLENDER_BIN" --background --command extension install "$ext_id" 2>/dev/null && {
        echo "    ✓ Installed via Extensions"
        return 0
    }
    echo "    ⚠ Extensions install failed, trying GitHub..."
    return 1
}

install_github_release() {
    local repo="$1"        # e.g. "nortikin/sverchok"
    local plugin_dir="$2"  # e.g. "sverchok"
    local url tmpzip branch

    echo ""
    echo "  → $repo"

    if [[ -d "$PLUGIN_DIR/$plugin_dir" ]]; then
        echo "    ✓ Already installed, updating..."
        (cd "$PLUGIN_DIR/$plugin_dir" && git pull --ff-only 2>/dev/null) || true
        return
    fi

    # Git clone (preferred)
    if command -v git &>/dev/null; then
        (cd "$PLUGIN_DIR" && git clone --depth 1 "https://github.com/$repo.git" "$plugin_dir" 2>/dev/null) && {
            echo "    ✓ Cloned from GitHub"
            return
        }
    fi

    # ZIP fallback — try master, main, then HEAD
    tmpzip=$(mktemp)
    for branch in master main HEAD; do
        url="https://github.com/$repo/archive/refs/heads/${branch}.zip"
        if curl -sLf "$url" -o "$tmpzip" 2>/dev/null; then
            unzip -qo "$tmpzip" -d "$PLUGIN_DIR" 2>/dev/null || true
            # The extracted dir is usually repo-branch or repo_name
            local extracted
            extracted=$(find "$PLUGIN_DIR" -maxdepth 1 -name "${repo#*/}-*" -type d 2>/dev/null | head -1)
            if [[ -n "$extracted" ]]; then
                mv "$extracted" "$PLUGIN_DIR/$plugin_dir" 2>/dev/null || true
            fi
            if [[ -d "$PLUGIN_DIR/$plugin_dir" ]]; then
                echo "    ✓ Downloaded ZIP ($branch)"
                rm -f "$tmpzip"
                return
            fi
        fi
    done
    echo "    ⚠ Could not download $repo (tried master, main, HEAD)"
    rm -f "$tmpzip"
}

enable_bundled() {
    local addon_name="$1"
    echo ""
    echo "  → $addon_name (bundled, enabling via script)"
    cat > /tmp/_blender_enable.py <<PYEOF
import bpy
try:
    bpy.ops.preferences.addon_enable(module="${addon_name}")
    print("✓ Enabled: ${addon_name}")
except Exception as e:
    print(f"⚠ Could not enable ${addon_name}: {e}")
PYEOF
    "$BLENDER_BIN" --background --python /tmp/_blender_enable.py 2>/dev/null
}

# ─── Install ─────────────────────────────────────────────────────────

install_all() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  🔌 Installing Blender plugins for agent ecosystem"
    echo "═══════════════════════════════════════════════════════════════"

    # ── Bundled (just enable) ────────────────────────────────────
    echo ""
    echo "━━━ Built-in addons (enabling) ─────────────────────────────"
    enable_bundled "io_scene_gltf2"       # glTF export — viktig för pipeline
    enable_bundled "node_wrangler"         # nod-genvägar

    # Dessa är inte längre inbyggda i Blender 5.2 — försök Extensions
    install_extension "mesh_f2" || true
    install_extension "mesh_looptools" || true
    install_extension "add_mesh_extra_objects" || true
    install_extension "io_fbx" || true

    # ── Community: Extensions + git/ZIP ──────────────────────
    echo ""
    echo "━━━ Community plugins ─────────────────────────────────────"

    # Procedural / parametric
    install_extension "sverchok" || install_github_release "nortikin/sverchok" "sverchok"
    install_extension "animation_nodes" || install_github_release "JacquesLucke/animation_nodes" "animation_nodes"

    # Mesh & geometry tools
    install_extension "mesh_machine" || install_github_release "maxivz/MeshMachine" "MeshMachine"
    install_extension "boxcutter" || install_github_release "lichtso/BoxCutter" "BoxCutter"
    install_extension "hardops" || install_github_release "hkjell/HardOps" "HardOps"

    # Material / shading
    install_extension "node_preview" || install_github_release "SamLPage/node_preview" "node_preview"
    install_extension "principled_baker" || install_github_release "blender-principled-baker/Principled-Baker" "principled_baker"
    install_extension "nodekit" || install_github_release "franMarz/NodeKit" "NodeKit"

    # UV / retopo
    install_extension "textools" || install_github_release "SavMartin/TexTools-Blender" "TexTools"
    install_extension "zen_uv" || install_github_release "mifth/mifthtools" "mifthtools"
    install_extension "retopoflow" || install_github_release "CGCookie/retopoflow" "retopoflow"
    install_extension "instant_meshes" || install_github_release "htkoca/InstantMeshesBlender" "instant_meshes"

    # Pipeline
    install_extension "better_fbx" || install_github_release "kshade/BetterFBX" "better_fbx"
    install_extension "cad_sketcher" || install_github_release "hlorus/CAD_Sketcher" "CAD_Sketcher"

    # Measurement
    install_extension "measureit" || install_github_release "gandalf3/measureit" "measureit"

    # AI / procedural
    install_extension "dream_textures" || install_github_release "carson-katri/dream-textures" "dream_textures"

    # ── pip for AI plugins ──────────────────────────────────────
    echo ""
    echo "━━━ Python dependencies (pip) ─────────────────────────────"
    pip3 install --quiet torch 2>/dev/null && echo "  ✓ torch" || echo "  ⚠ torch (skip: no GPU or pip issue)"
    pip3 install --quiet diffusers 2>/dev/null && echo "  ✓ diffusers" || true
    pip3 install --quiet transformers 2>/dev/null && echo "  ✓ transformers" || true

    # ── Verify ──────────────────────────────────────────────────
    echo ""
    echo "━━━ Installed plugins ────────────────────────────────────"
    ls -1 "$PLUGIN_DIR" 2>/dev/null | grep -v __pycache__ | head -30
    local count
    count=$(ls -1 "$PLUGIN_DIR" 2>/dev/null | grep -vc __pycache__ || true)
    echo ""
    echo "  $count plugins in $PLUGIN_DIR"
    echo ""
    echo "✓ Done!"
    echo ""
    echo "🔧 Enable: Öppna Blender → Preferences → Add-ons, sök och bocka i:"
    echo "   • Sverchok  • Animation Nodes  • TexTools"
    echo "   • RetopoFlow  • CAD Sketcher  • Dream Textures  • MeasureIt"
    echo ""
    echo "📌 Manually install via Blender → Preferences → Add-ons → Get Extensions:"
    echo "   • Mesh Machine   • BoxCutter   • HardOps"
    echo "   • Node Preview   • Principled Baker   • NodeKit"
    echo "   • Instant Meshes • Better FBX"
    echo "   • F2, Loop Tools, Extra Objects, FBX (bundled in older Blender)"
}

# ─── Main ──────────────────────────────────────────────────────────────

echo "🔍 Detecting Blender..."
detect_blender
install_all
