import type { ConfirmedItem } from './campus-workflow'
import type { RecyclingPoint } from './recycling-points'

export type Coordinates = { latitude: number; longitude: number }

export type PointRecommendation = {
  point: RecyclingPoint
  matchedMaterials: string[]
  unmatchedMaterials: string[]
  distanceKm: number
}

function key(value: string): string {
  return value.trim().toLocaleLowerCase()
}

export function conditionConfirmedForRecycling(item: ConfirmedItem): boolean {
  if (item.category !== 'Recyclable Waste') return false
  return (item.questions ?? []).every((question) => {
    if (question.key === 'material') return item.material.trim() !== '' && key(item.material) !== 'unknown'
    if (question.key === 'hazardous_contents') return item.condition_answers?.hazardous_contents === false
    return item.condition_answers?.[question.key] === true
  })
}

export function straightLineDistanceKm(first: Coordinates, second: Coordinates): number {
  const radians = Math.PI / 180
  const latitudeDifference = (second.latitude - first.latitude) * radians
  const longitudeDifference = (second.longitude - first.longitude) * radians
  const arc = Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos(first.latitude * radians) * Math.cos(second.latitude * radians) *
    Math.sin(longitudeDifference / 2) ** 2
  return 6371 * 2 * Math.atan2(Math.sqrt(arc), Math.sqrt(1 - arc))
}

export function recommendPoints(
  points: RecyclingPoint[], items: ConfirmedItem[], origin: Coordinates,
): PointRecommendation[] {
  const materials = [...new Map(items
    .filter(item => conditionConfirmedForRecycling(item) && key(item.material) !== 'unknown')
    .map(item => [key(item.material), item.material.trim()])).values()]
  return points.filter(point => point.active !== false).flatMap(point => {
    const accepted = new Set(point.accepted_materials.map(key))
    const matchedMaterials = materials.filter(material => accepted.has(key(material)))
    if (matchedMaterials.length === 0) return []
    return [{
      point,
      matchedMaterials,
      unmatchedMaterials: materials.filter(material => !accepted.has(key(material))),
      distanceKm: straightLineDistanceKm(origin, point),
    }]
  }).sort((first, second) => first.distanceKm - second.distanceKm || first.point.name.localeCompare(second.point.name))
}
