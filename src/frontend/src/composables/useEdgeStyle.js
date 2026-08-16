import { Position } from '@vue-flow/core'

// Asymmetric S-curve for the canvas's custom edges.
//
// A faithful copy of @vue-flow/core's getBezierPath internals, but with
// separate source/target curvature so the two ends can be tuned independently.
// Keeping the library's position-aware control points is what makes an edge
// spring out of its source handle and approach its target handle along their
// axes, instead of starting "behind" a node.
export const SOURCE_CURVATURE = 0.2
export const TARGET_CURVATURE = 0.4

function calculateControlOffset(distance, curvature) {
  if (distance >= 0) return 0.5 * distance
  return curvature * 25 * Math.sqrt(-distance)
}

function controlWithCurvature({ pos, x1, y1, x2, y2, c }) {
  switch (pos) {
    case Position.Left:
      return [x1 - calculateControlOffset(x1 - x2, c), y1]
    case Position.Right:
      return [x1 + calculateControlOffset(x2 - x1, c), y1]
    case Position.Top:
      return [x1, y1 - calculateControlOffset(y1 - y2, c)]
    case Position.Bottom:
    default:
      return [x1, y1 + calculateControlOffset(y2 - y1, c)]
  }
}

export function asymmetricBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition }) {
  const [scx, scy] = controlWithCurvature({
    pos: sourcePosition,
    x1: sourceX,
    y1: sourceY,
    x2: targetX,
    y2: targetY,
    c: SOURCE_CURVATURE,
  })
  const [tcx, tcy] = controlWithCurvature({
    pos: targetPosition,
    x1: targetX,
    y1: targetY,
    x2: sourceX,
    y2: sourceY,
    c: TARGET_CURVATURE,
  })

  const path = `M${sourceX},${sourceY} C${scx},${scy} ${tcx},${tcy} ${targetX},${targetY}`
  const labelX = sourceX * 0.125 + scx * 0.375 + tcx * 0.375 + targetX * 0.125
  const labelY = sourceY * 0.125 + scy * 0.375 + tcy * 0.375 + targetY * 0.125
  return [path, labelX, labelY, 0, 0]
}
