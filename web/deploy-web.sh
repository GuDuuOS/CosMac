#!/usr/bin/env bash
# ============================================================
# CosMac Star 网页层部署脚本
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
# 统一品牌：Element 的 favicon/登录 logo 也用新版 CosMac Star logo（正方形 1080）
LOGO="$REPO_DIR/web/landing/logo.png"
LANDING_LOGO="$REPO_DIR/web/landing/logo.png"
LANDING_LOGO_SVG="$REPO_DIR/web/landing/logo.svg"

echo "仓库目录: $REPO_DIR"

# 1) 落地页（cosmac.cc）
mkdir -p "$LANDING_DIR"
cp "$REPO_DIR/web/landing/index.html" "$LANDING_DIR/index.html"
cp "$LANDING_LOGO" "$LANDING_DIR/logo.png"
cp "$LANDING_LOGO_SVG" "$LANDING_DIR/logo.svg"
cp "$REPO_DIR/web/landing/guduu-star-hero.png" "$LANDING_DIR/guduu-star-hero.png"
cp "$REPO_DIR/web/landing/star-main.jpeg" "$LANDING_DIR/star-main.jpeg"
cp "$REPO_DIR"/web/landing/star-look-*.jpg "$LANDING_DIR"/
echo "✅ 落地页已更新"

# 2) Element 配置 + 登录页 logo（app.cosmac.cc）
cp "$REPO_DIR/web/element-config.json" "$ELEMENT_DIR/config.json"
cp "$LOGO" "$ELEMENT_DIR/cosmac-logo.png"
cp "$REPO_DIR/web/element-auth.css" "$ELEMENT_DIR/cosmac-auth.css"
echo "✅ Element 配置已更新"

# 3) 注入注册/登录页品牌背景样式；Element 升级后重跑脚本即可恢复。
if ! grep -q 'cosmac-auth.css' "$ELEMENT_DIR/index.html"; then
  sed -i '/<\/head>/i\  <link rel="stylesheet" href="/cosmac-auth.css">' "$ELEMENT_DIR/index.html"
fi
echo "✅ Element 注册/登录页背景样式已注入"

# 4) 去掉 Element 品牌字样：标签页标题 / meta / PWA 名称
#    （只改给人看的文本，不动 themes/element 等路径）
sed -i 's#<title>[^<]*</title>#<title>CosMac Star</title>#' "$ELEMENT_DIR/index.html"
sed -i 's/content="\([^"]*\)Element\([^"]*\)"/content="\1CosMac Star\2"/g' "$ELEMENT_DIR/index.html"
[ -f "$ELEMENT_DIR/manifest.json" ] && sed -i 's/"Element"/"CosMac Star"/g' "$ELEMENT_DIR/manifest.json"
echo "✅ Element 静态品牌已替换为 CosMac Star"

# 5) 所有图标（标签页 favicon + 添加到主屏图标）换成 CosMac Star logo
for f in "$ELEMENT_DIR"/vector-icons/*.png; do
  [ -f "$f" ] || continue
  w=$(identify -format "%w" "$f" 2>/dev/null) || continue
  convert "$LOGO" -resize "${w}x${w}!" "$f"
done
# 浏览器默认请求的 /favicon.ico
convert "$LOGO" -resize "64x64!" "$ELEMENT_DIR/favicon.ico"
convert "$LANDING_LOGO" -resize "64x64!" "$LANDING_DIR/favicon.ico"
# 标签 favicon 缓存绕过：vector-icons 是 hash 命名、被浏览器永久缓存，
# 改内容没用；另存一个新文件名并把 index.html 的图标链接指向它，强制刷新。
convert "$LOGO" -resize "256x256!" "$ELEMENT_DIR/cosmac-icon.png"
sed -i 's#href="vector-icons/[^"]*\.png"#href="/cosmac-icon.png"#g' "$ELEMENT_DIR/index.html"
echo "✅ 图标已全部替换（标签图标已指向新文件名绕过缓存）"

# 6) 应用内 logo（登录后首页/加载页/分享预览）换成 CosMac Star logo
#    .svg 用矢量版覆盖（保持类型）；.png 用位图版缩到 512 保持轻量
for t in \
  "$ELEMENT_DIR/themes/element/img/logos/element-logo.svg" \
  "$ELEMENT_DIR/mobile_guide/assets/element-logo.svg" \
  "$ELEMENT_DIR"/img/element-desktop-logo.*.svg; do
  [ -f "$t" ] && cp "$LANDING_LOGO_SVG" "$t"
done
for t in \
  "$ELEMENT_DIR/themes/element/img/logos/element-app-logo.png" \
  "$ELEMENT_DIR/themes/element/img/logos/opengraph.png"; do
  [ -f "$t" ] && convert "$LOGO" -resize 512x512 "$t"
done
echo "✅ 应用内 logo 已替换"

echo "🎉 网页层部署完成"
