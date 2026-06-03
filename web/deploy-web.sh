#!/usr/bin/env bash
# ============================================================
# GuDuu 网页层部署脚本
# 把本仓库的网页定制（落地页 / Element 配置 / 品牌 / logo / favicon）
# 应用到服务器。可重复运行（幂等）；Element 升级后重跑即可重新套用品牌。
#
# 用法（服务器上，先 git pull 再跑）：
#   sudo bash /opt/guduu/app/web/deploy-web.sh
#
# 前提：/var/www/element 已部署 Element 网页版；/var/www/cosmac-landing 存在；
#       服务器已装 imagemagick（convert / identify）。
# ============================================================
set -e

# 仓库根目录（脚本在 <repo>/web/ 下）
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ELEMENT_DIR=/var/www/element
LANDING_DIR=/var/www/cosmac-landing
LOGO="$REPO_DIR/LOGO/logo.png"

echo "仓库目录: $REPO_DIR"

# 1) 落地页（cosmac.cc）
mkdir -p "$LANDING_DIR"
cp "$REPO_DIR/web/landing/index.html" "$LANDING_DIR/index.html"
cp "$LOGO" "$LANDING_DIR/logo.png"
echo "✅ 落地页已更新"

# 2) Element 配置 + 登录页 logo（app.cosmac.cc）
cp "$REPO_DIR/web/element-config.json" "$ELEMENT_DIR/config.json"
cp "$LOGO" "$ELEMENT_DIR/guduu-logo.png"
echo "✅ Element 配置已更新"

# 3) 去掉 Element 品牌字样：标签页标题 / meta / PWA 名称
#    （只改给人看的文本，不动 themes/element 等路径）
sed -i 's#<title>[^<]*</title>#<title>GuDuu</title>#' "$ELEMENT_DIR/index.html"
sed -i 's/content="\([^"]*\)Element\([^"]*\)"/content="\1GuDuu\2"/g' "$ELEMENT_DIR/index.html"
[ -f "$ELEMENT_DIR/manifest.json" ] && sed -i 's/"Element"/"GuDuu"/g' "$ELEMENT_DIR/manifest.json"
echo "✅ Element 静态品牌已替换为 GuDuu"

# 4) 所有图标（标签页 favicon + 添加到主屏图标）换成 GuDuu logo
for f in "$ELEMENT_DIR"/vector-icons/*.png; do
  [ -f "$f" ] || continue
  w=$(identify -format "%w" "$f" 2>/dev/null) || continue
  convert "$LOGO" -resize "${w}x${w}!" "$f"
done
# 浏览器默认请求的 /favicon.ico
convert "$LOGO" -resize "64x64!" "$ELEMENT_DIR/favicon.ico"
convert "$LOGO" -resize "64x64!" "$LANDING_DIR/favicon.ico"
echo "✅ 图标已全部替换"

echo "🎉 网页层部署完成"
