import { supabase } from '../../lib/supabase'
import type {
  Achievement,
  CommunityImpact,
  LeaderboardEntry,
  RewardTransaction,
  TitleDefinition,
} from '../../types'

export interface MemberRewardData {
  achievements: Achievement[]
  transactions: RewardTransaction[]
  titles: TitleDefinition[]
  pointsRank?: number
  reportsRank?: number
}

export async function getLeaderboard(): Promise<LeaderboardEntry[]> {
  const { data, error } = await supabase
    .from('leaderboard_view')
    .select('user_id, full_name, total_points, valid_report_count, current_title')

  if (error) throw error
  return (data ?? []).map((entry) => ({
    id: String(entry.user_id),
    name: String(entry.full_name),
    title: String(entry.current_title ?? 'No title yet'),
    points: Number(entry.total_points ?? 0),
    validReports: Number(entry.valid_report_count ?? 0),
  }))
}

export async function getMyImpact(): Promise<CommunityImpact> {
  const { data, error } = await supabase
    .from('my_impact')
    .select(`
      total_points,
      verified_reports,
      cases_resolved,
      locations_currently_handled,
      achievements_unlocked,
      current_title,
      unread_impact_notifications
    `)
    .single()

  if (error) throw error

  return {
    totalPoints: Number(data.total_points ?? 0),
    verifiedReports: Number(data.verified_reports ?? 0),
    casesResolved: Number(data.cases_resolved ?? 0),
    locationsCurrentlyHandled: Number(data.locations_currently_handled ?? 0),
    achievementsUnlocked: Number(data.achievements_unlocked ?? 0),
    currentTitle: String(data.current_title ?? 'No title yet'),
    unreadImpactNotifications: Number(data.unread_impact_notifications ?? 0),
  }
}

export async function getMemberRewardData(userId: string): Promise<MemberRewardData> {
  const [achievementsResult, unlockedResult, transactionsResult, titlesResult, rankResult] =
    await Promise.all([
      supabase
        .from('achievements')
        .select(`
          achievement_id,
          achievement_name,
          description,
          criteria_type,
          criteria_value,
          bonus_points,
          title:titles(title_name)
        `)
        .order('criteria_value'),
      supabase
        .from('user_achievements')
        .select('achievement_id')
        .eq('user_id', userId),
      supabase
        .from('reward_transactions')
        .select(`
          transaction_id,
          report_id,
          points,
          description,
          awarded_at,
          rule:reward_rules(reward_type)
        `)
        .eq('user_id', userId)
        .order('awarded_at', { ascending: false })
        .limit(20),
      supabase
        .from('titles')
        .select('title_id, title_name, description, minimum_points')
        .order('minimum_points'),
      supabase
        .from('leaderboard_view')
        .select('points_rank, reports_rank')
        .eq('user_id', userId)
        .maybeSingle(),
    ])

  const error =
    achievementsResult.error ??
    unlockedResult.error ??
    transactionsResult.error ??
    titlesResult.error ??
    rankResult.error
  if (error) throw error

  const unlocked = new Set(
    (unlockedResult.data ?? []).map((entry) => String(entry.achievement_id)),
  )

  return {
    achievements: (achievementsResult.data ?? []).map((entry) => {
      const title = Array.isArray(entry.title) ? entry.title[0] : entry.title
      return {
        id: String(entry.achievement_id),
        name: String(entry.achievement_name),
        description: String(entry.description),
        pointsRequired:
          entry.criteria_type === 'points' ? Number(entry.criteria_value) : 0,
        title: String(title?.title_name ?? 'No title yet'),
        criteriaType: entry.criteria_type as 'points' | 'valid_reports',
        criteriaValue: Number(entry.criteria_value),
        bonusPoints: Number(entry.bonus_points ?? 0),
        unlocked: unlocked.has(String(entry.achievement_id)),
      }
    }),
    transactions: (transactionsResult.data ?? []).map((entry) => {
      const rule = Array.isArray(entry.rule) ? entry.rule[0] : entry.rule
      return {
        id: String(entry.transaction_id),
        reportId: entry.report_id ? String(entry.report_id) : undefined,
        points: Number(entry.points),
        description: String(entry.description),
        awardedAt: String(entry.awarded_at),
        rewardType: String(rule?.reward_type ?? 'reward'),
      }
    }),
    titles: (titlesResult.data ?? []).map((title) => ({
      id: String(title.title_id),
      name: String(title.title_name),
      description: String(title.description),
      minimumPoints: Number(title.minimum_points),
    })),
    pointsRank: rankResult.data?.points_rank
      ? Number(rankResult.data.points_rank)
      : undefined,
    reportsRank: rankResult.data?.reports_rank
      ? Number(rankResult.data.reports_rank)
      : undefined,
  }
}
