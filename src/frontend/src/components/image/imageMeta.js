/**
 * The small facts every image surface needs — in one place ([[B211]]).
 *
 * These were copied per surface before: `formatSize` and `formatBytes` were two
 * functions in two files, "can this be cut out?" was written once in the trait
 * editor and again (inverted) in the viewer, and the thumbnail rule was repeated
 * four times. A picture is one thing, so its caption and its capabilities should
 * be one thing too.
 */

/** The canonical role tags, in the order a surface lists them. */
export const ROLE_TAGS = [
  { key: 'sheet', label: 'Sheet', title: 'The character sheet / trait row picture' },
  { key: 'background', label: 'BG', title: 'The full-bleed backdrop' },
  { key: 'navdot', label: 'Nav', title: 'The marker in the location viewer' },
]

/**
 * Labels the **pipelines** set, shown but never editable — `imagen` owns
 * `ai_generated`, `animate` owns `ai_animated`. `ai` is the human's own tick and
 * lives beside them in the viewer.
 */
export const AUTO_FLAG_LABELS = {
  ai_generated: 'AI-generated',
  ai_animated: 'AI-animated',
}

export function formatSize(bytes) {
  if (!bytes || bytes === 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1048576).toFixed(1)} MB`
}

export function caption(image) {
  if (!image) return ''
  const size = formatSize(image.size_bytes)
  return size ? `${image.image_type} — ${size}` : `${image.image_type}`
}

/**
 * What a **gallery** shows: the loop if the picture has one, because the motion is
 * the point, otherwise the still. Never the matte — a grid of transparent
 * cut-outs would read as holes rather than pictures; that view belongs in the
 * viewer, where you are inspecting one.
 */
export function thumbSrc(image) {
  if (!image) return ''
  if ((image.renders || []).includes('animated') && image.path_animated) return image.path_animated
  return image.path_large || image.path_xlarge || ''
}

/** What the **viewer** shows: the loop, else the matte, else the still. */
export function detailSrc(image) {
  if (!image) return ''
  const renders = image.renders || []
  if (renders.includes('animated') && image.path_animated) return image.path_animated
  if (renders.includes('cutout') && image.path_cutout) return image.path_cutout
  return image.path_large || image.path_xlarge || ''
}

/** A picture that already has a matte or a loop has nothing left to cut out. */
export function canCutOut(image) {
  const renders = (image && image.renders) || []
  return !!image && !renders.includes('cutout') && !renders.includes('animated')
}

/** The server owns the 2048px ceiling; `can_upscale` is its answer. */
export function canUpscale(image) {
  return image?.can_upscale === true
}

/** The machine-set flags present on a picture, in a stable order. */
export function autoFlags(image) {
  const flags = (image && image.flags) || []
  return Object.keys(AUTO_FLAG_LABELS).filter(f => flags.includes(f))
}

export function hasFlag(image, flag) {
  return ((image && image.flags) || []).includes(flag)
}

export function hasProvenance(image) {
  return !!image
    && ((image.credits || []).length > 0 || !!image.license || !!image.credit_text)
}
