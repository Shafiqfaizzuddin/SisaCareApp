import type { Achievement } from '../../types'

export const achievements: Achievement[] = [
  {
    id: 'first-report',
    name: 'First Step',
    description: 'Submit your first valid community report.',
    pointsRequired: 50,
    title: 'Community Starter',
  },
  {
    id: 'clean-streets',
    name: 'Clean Streets',
    description: 'Help verify five illegal dumping locations.',
    pointsRequired: 250,
    title: 'Neighbourhood Scout',
  },
  {
    id: 'waste-watcher',
    name: 'Waste Watcher',
    description: 'Reach 500 points through valid reports.',
    pointsRequired: 500,
    title: 'Waste Watcher',
  },
  {
    id: 'guardian',
    name: 'Community Guardian',
    description: 'Make a sustained contribution worth 1,000 points.',
    pointsRequired: 1000,
    title: 'Community Guardian',
  },
]

export function memberTitleForPoints(points: number): string {
  return achievements.reduce(
    (title, achievement) =>
      points >= achievement.pointsRequired ? achievement.title : title,
    'Community Member',
  )
}
