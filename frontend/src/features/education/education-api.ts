import { supabase } from '../../lib/supabase'
import type { EducationalContent, WasteCategory } from '../../types'

function mapContent(entry: Record<string, unknown>): EducationalContent {
  return {
    id: String(entry.content_id),
    title: String(entry.title),
    content: String(entry.content),
    category: String(entry.category) as WasteCategory,
    imageUrl: entry.image_url ? String(entry.image_url) : undefined,
    status: String(entry.status) as 'draft' | 'published',
    publishedAt: entry.published_at ? String(entry.published_at) : undefined,
    createdAt: String(entry.created_at),
    updatedAt: String(entry.updated_at),
  }
}

export async function getPublishedEducation(): Promise<EducationalContent[]> {
  const { data, error } = await supabase
    .from('educational_content')
    .select('*')
    .eq('status', 'published')
    .order('published_at', { ascending: false })
  if (error) throw error
  return (data as unknown as Record<string, unknown>[]).map(mapContent)
}

export async function getAdminEducation(): Promise<EducationalContent[]> {
  const { data, error } = await supabase
    .from('educational_content')
    .select('*')
    .order('updated_at', { ascending: false })
  if (error) throw error
  return (data as unknown as Record<string, unknown>[]).map(mapContent)
}

export interface EducationInput {
  id?: string
  title: string
  content: string
  category: WasteCategory
  imageUrl?: string
  status: 'draft' | 'published'
  createdBy: string
}

export async function saveEducation(input: EducationInput): Promise<void> {
  const payload = {
    title: input.title.trim(),
    content: input.content.trim(),
    category: input.category,
    image_url: input.imageUrl?.trim() || null,
    status: input.status,
    created_by: input.createdBy,
  }

  const query = input.id
    ? supabase.from('educational_content').update(payload).eq('content_id', input.id)
    : supabase.from('educational_content').insert(payload)
  const { error } = await query
  if (error) throw error
}

export async function deleteEducation(contentId: string): Promise<void> {
  const { error } = await supabase
    .from('educational_content')
    .delete()
    .eq('content_id', contentId)
  if (error) throw error
}
