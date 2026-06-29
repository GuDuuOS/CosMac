/**
 * 安全的 Markdown 渲染（共享）。
 *
 * 安全模型（与聊天气泡那版同源、同样加固）：
 *  1) 先整体 HTML 转义（含 " 和 '），任何 <script>/属性击穿都失效；
 *  2) 先把代码块/行内代码"抠出来"存进 stash 占位，避免里面的符号被二次处理；
 *  3) 链接/图片 URL 只允许 http(s)（mailto 仅链接），且 URL 已被转义（引号→&quot;）不会击穿属性；
 *  4) 渲染前剥掉占位哨兵 \x00，防用户原文污染还原逻辑。
 *
 * 比聊天版多支持：标题(#/##/###)、无序/有序列表、引用块、图片 ![]()——教学文档要用。
 * 返回的 HTML 仅含我们自己拼的白名单标签，可安全用于 v-html。
 */

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** 行内格式：加粗/斜体/删除线/图片/链接/@提及。传入的文本必须已 escapeHtml 过。 */
function inline(s: string): string {
  // 图片要在链接之前处理（语法 ![]() 是 []() 的超集）
  s = s.replace(
    /!\[([^\]\n]*)\]\((https?:\/\/[^\s)]+)\)/g,
    '<img alt="$1" src="$2" class="md-img" loading="lazy">',
  )
  s = s.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
  s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  s = s.replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
  s = s.replace(
    /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  )
  s = s.replace(
    /(^|[\s(])@([a-zA-Z0-9_.\-]+(?::[a-zA-Z0-9_.\-]+)?)/g,
    '$1<span class="mention">@$2</span>',
  )
  return s
}

export function renderMarkdown(raw: string): string {
  const stash: string[] = []
  const keep = (html: string) => `\x00${stash.push(html) - 1}\x00`
  // 1) 转义 + 剥哨兵
  let text = escapeHtml((raw || '').replace(/\x00/g, ''))
  // 2) 抠出代码块/行内代码（其内容不再做任何 markdown 替换）
  text = text.replace(/```([\s\S]*?)```/g, (_m, c) =>
    keep(`<pre class="md-pre">${c.replace(/^\n|\n$/g, '')}</pre>`),
  )
  text = text.replace(/`([^`\n]+)`/g, (_m, c) => keep(`<code class="md-code">${c}</code>`))

  // 3) 逐行做块级解析（标题/列表/引用/段落）
  const lines = text.split('\n')
  const out: string[] = []
  let listType: 'ul' | 'ol' | null = null
  let para: string[] = []
  let quote: string[] = []

  const flushPara = () => {
    if (para.length) { out.push(`<p>${inline(para.join('<br>'))}</p>`); para = [] }
  }
  const flushList = () => {
    if (listType) { out.push(`</${listType}>`); listType = null }
  }
  const flushQuote = () => {
    if (quote.length) {
      out.push(`<blockquote>${inline(quote.join('<br>'))}</blockquote>`)
      quote = []
    }
  }
  const flushAll = () => { flushPara(); flushList(); flushQuote() }

  for (const line of lines) {
    const isPlaceholder = /^\x00\d+\x00$/.test(line.trim())
    if (isPlaceholder) {            // 代码块占位整行原样输出
      flushAll()
      out.push(line.trim())
      continue
    }
    const h = line.match(/^(#{1,3})\s+(.*)$/)
    if (h) { flushAll(); const n = h[1].length; out.push(`<h${n}>${inline(h[2])}</h${n}>`); continue }

    const ul = line.match(/^[-*]\s+(.*)$/)
    const ol = line.match(/^\d+\.\s+(.*)$/)
    if (ul || ol) {
      flushPara(); flushQuote()
      const want: 'ul' | 'ol' = ul ? 'ul' : 'ol'
      if (listType !== want) { flushList(); out.push(`<${want}>`); listType = want }
      out.push(`<li>${inline((ul ? ul[1] : (ol as RegExpMatchArray)[1]))}</li>`)
      continue
    }

    const q = line.match(/^>\s?(.*)$/)
    if (q) { flushPara(); flushList(); quote.push(q[1]); continue }

    if (line.trim() === '') { flushAll(); continue }  // 空行 = 段落分隔
    flushList(); flushQuote()
    para.push(line)
  }
  flushAll()

  // 4) 还原代码占位
  let html = out.join('\n')
  html = html.replace(/\x00(\d+)\x00/g, (_m, i) => stash[+i] ?? '')
  return html
}
