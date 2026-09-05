// Minimal, XSS-safe markdown renderer for the Blue Book.
//
// Strategy: escape all HTML first, then apply markdown transforms on the
// *escaped* text. User input can never inject raw HTML — links are additionally
// allow-listed to http(s)/relative/`#` URLs only. No external dependency.

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function inline(text) {
  let out = text
  // Inline code (before bold/italic so backticks aren't interpreted as text)
  out = out.replace(/`([^`]+)`/g, '<code>$1</code>')
  // Bold
  out = out.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  out = out.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  // Italic
  out = out.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  out = out.replace(/_([^_]+)_/g, '<em>$1</em>')
  // Links [label](url) — only http(s), relative, or hash URLs
  out = out.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, url) => {
    if (/^(https?:\/\/|\/|#)/i.test(url)) {
      return `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
    }
    return label
  })
  return out
}

export function renderMarkdown(src) {
  if (!src) return ''
  const lines = escapeHtml(src).split('\n')
  const out = []
  let inCode = false
  let codeBuf = []
  let listType = null // 'ul' | 'ol' | null

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`)
      listType = null
    }
  }

  for (const line of lines) {
    const trimmed = line.trim()

    // Fenced code block
    if (trimmed.startsWith('```')) {
      if (inCode) {
        out.push(`<pre><code>${codeBuf.join('\n')}</code></pre>`)
        codeBuf = []
        inCode = false
      } else {
        closeList()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }

    // Blank line closes a list
    if (!trimmed) {
      closeList()
      continue
    }

    // Headings
    const h = /^(#{1,6})\s+(.*)$/.exec(trimmed)
    if (h) {
      closeList()
      const level = h[1].length
      out.push(`<h${level}>${inline(h[2])}</h${level}>`)
      continue
    }

    // Unordered list
    const ul = /^[-*+]\s+(.*)$/.exec(trimmed)
    if (ul) {
      if (listType !== 'ul') {
        closeList()
        out.push('<ul>')
        listType = 'ul'
      }
      out.push(`<li>${inline(ul[1])}</li>`)
      continue
    }

    // Ordered list
    const ol = /^\d+[.)]\s+(.*)$/.exec(trimmed)
    if (ol) {
      if (listType !== 'ol') {
        closeList()
        out.push('<ol>')
        listType = 'ol'
      }
      out.push(`<li>${inline(ol[1])}</li>`)
      continue
    }

    // Blockquote
    const bq = /^>\s?(.*)$/.exec(trimmed)
    if (bq) {
      closeList()
      out.push(`<blockquote>${inline(bq[1])}</blockquote>`)
      continue
    }

    // Paragraph
    closeList()
    out.push(`<p>${inline(trimmed)}</p>`)
  }

  if (inCode) out.push(`<pre><code>${codeBuf.join('\n')}</code></pre>`)
  closeList()
  return out.join('')
}
