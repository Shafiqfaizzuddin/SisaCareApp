import type {
  Achievement,
  LeaderboardEntry,
  UserProfile,
} from '../../types'

export const demoMember: UserProfile = {
  id: 'usr-204',
  name: 'Aiman Rahman',
  email: 'aiman.rahman@example.com',
  role: 'user',
  points: 420,
  title: 'Neighbourhood Scout',
  rank: 4,
  validReports: 11,
}

export const demoAdmin: UserProfile = {
  id: 'adm-001',
  name: 'Shafiq Faizzuddin',
  email: 'shafiq@council.gov.my',
  role: 'admin',
  points: 0,
  title: 'Municipal Administrator',
}

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

export const leaderboardEntries: LeaderboardEntry[] = [
  {
    id: 'usr-188',
    name: 'Nur Izzati',
    title: 'Community Guardian',
    points: 1280,
    validReports: 31,
  },
  {
    id: 'usr-193',
    name: 'Daniel Lee',
    title: 'Waste Watcher',
    points: 910,
    validReports: 24,
  },
  {
    id: 'usr-176',
    name: 'Siti Hajar',
    title: 'Waste Watcher',
    points: 680,
    validReports: 19,
  },
  {
    id: demoMember.id,
    name: demoMember.name,
    title: demoMember.title,
    points: demoMember.points,
    validReports: demoMember.validReports ?? 0,
    isCurrentUser: true,
  },
  {
    id: 'usr-221',
    name: 'Kumar Raj',
    title: 'Community Starter',
    points: 310,
    validReports: 8,
  },
  {
    id: 'usr-229',
    name: 'Mei Xin',
    title: 'Community Starter',
    points: 190,
    validReports: 5,
  },
]
