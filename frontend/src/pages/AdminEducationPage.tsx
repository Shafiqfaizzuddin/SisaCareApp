import {
  BookOpen,
  FilePenLine,
  Globe2,
  Plus,
  Save,
  Trash2,
  X,
} from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import {
  deleteEducation,
  getAdminEducation,
  saveEducation,
  type EducationInput,
} from '../features/education/education-api'
import { useRole } from '../features/authentication/useRole'
import { wasteCategoryOptions } from '../features/reporting/categories'
import type { EducationalContent, WasteCategory } from '../types'

interface ContentForm {
  id?: string
  title: string
  content: string
  category: WasteCategory
  imageUrl: string
  status: 'draft' | 'published'
}

const emptyForm: ContentForm = {
  title: '',
  content: '',
  category: 'household',
  imageUrl: '',
  status: 'draft',
}

export function AdminEducationPage() {
  const { user } = useRole()
  const queryClient = useQueryClient()
  const [form, setForm] = useState<ContentForm>(emptyForm)
  const [showEditor, setShowEditor] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const contentQuery = useQuery({
    queryKey: ['admin-education'],
    queryFn: getAdminEducation,
  })

  async function refreshContent() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['admin-education'] }),
      queryClient.invalidateQueries({ queryKey: ['published-education'] }),
    ])
  }

  const saveMutation = useMutation({
    mutationFn: (input: EducationInput) => saveEducation(input),
    onSuccess: async () => {
      setError(null)
      setForm(emptyForm)
      setShowEditor(false)
      await refreshContent()
    },
    onError: (mutationError) => setError(mutationError.message),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteEducation,
    onSuccess: refreshContent,
    onError: (mutationError) => setError(mutationError.message),
  })

  function editContent(content: EducationalContent) {
    setForm({
      id: content.id,
      title: content.title,
      content: content.content,
      category: content.category,
      imageUrl: content.imageUrl ?? '',
      status: content.status,
    })
    setError(null)
    setShowEditor(true)
  }

  function closeEditor() {
    setForm(emptyForm)
    setError(null)
    setShowEditor(false)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!user) return
    saveMutation.mutate({ ...form, createdBy: user.id })
  }

  return (
    <>
      <header className="admin-page-heading">
        <div>
          <p className="eyebrow">Public awareness</p>
          <h1>Educational content</h1>
          <p>Create guidance and control what appears on the public education page.</p>
        </div>
        <button
          className="button button--primary"
          type="button"
          onClick={() => {
            setForm(emptyForm)
            setShowEditor(true)
          }}
        >
          <Plus size={17} /> New content
        </button>
      </header>

      {showEditor && (
        <section className="admin-panel content-editor">
          <header className="admin-panel__heading">
            <div><h2>{form.id ? 'Edit content' : 'Create content'}</h2><p>Published entries become visible immediately.</p></div>
            <button className="icon-button" type="button" aria-label="Close editor" title="Close editor" onClick={closeEditor}><X size={18} /></button>
          </header>
          {error && <p className="form-error" role="alert">{error}</p>}
          <form onSubmit={handleSubmit}>
            <div className="content-editor__grid">
              <div className="field">
                <label htmlFor="content-title">Title</label>
                <input id="content-title" value={form.title} onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))} required />
              </div>
              <div className="field">
                <label htmlFor="content-category">Category</label>
                <select id="content-category" value={form.category} onChange={(event) => setForm((current) => ({ ...current, category: event.target.value as WasteCategory }))}>
                  {wasteCategoryOptions.map((category) => <option key={category.value} value={category.value}>{category.label}</option>)}
                </select>
              </div>
            </div>
            <div className="field">
              <label htmlFor="content-body">Guidance</label>
              <textarea id="content-body" rows={6} value={form.content} onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))} required />
            </div>
            <div className="content-editor__grid">
              <div className="field">
                <label htmlFor="content-image">Image URL</label>
                <input id="content-image" type="url" placeholder="Optional HTTPS image URL" value={form.imageUrl} onChange={(event) => setForm((current) => ({ ...current, imageUrl: event.target.value }))} />
              </div>
              <div className="field">
                <label htmlFor="content-status">Publication status</label>
                <select id="content-status" value={form.status} onChange={(event) => setForm((current) => ({ ...current, status: event.target.value as 'draft' | 'published' }))}>
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                </select>
              </div>
            </div>
            <div className="content-editor__actions">
              <button className="button button--secondary" type="button" onClick={closeEditor}>Cancel</button>
              <button className="button button--primary" type="submit" disabled={saveMutation.isPending}><Save size={17} /> {saveMutation.isPending ? 'Saving...' : 'Save content'}</button>
            </div>
          </form>
        </section>
      )}

      <section className="admin-panel content-list">
        <header className="admin-panel__heading">
          <div><h2>Content library</h2><p>{contentQuery.data?.length ?? 0} entries</p></div>
          <BookOpen size={20} />
        </header>
        {contentQuery.isLoading ? (
          <p className="empty-state">Loading content...</p>
        ) : contentQuery.isError ? (
          <p className="form-error">Content could not be loaded.</p>
        ) : (
          <div className="content-list__items">
            {(contentQuery.data ?? []).map((content) => (
              <article key={content.id}>
                <span className={`content-status content-status--${content.status}`}>
                  {content.status === 'published' ? <Globe2 size={14} /> : <FilePenLine size={14} />}
                  {content.status}
                </span>
                <div>
                  <small>{wasteCategoryOptions.find((category) => category.value === content.category)?.label}</small>
                  <h3>{content.title}</h3>
                  <p>{content.content}</p>
                </div>
                <div className="content-list__actions">
                  <button className="icon-button" type="button" aria-label={`Edit ${content.title}`} title="Edit" onClick={() => editContent(content)}><FilePenLine size={17} /></button>
                  <button
                    className="icon-button icon-button--danger"
                    type="button"
                    aria-label={`Delete ${content.title}`}
                    title="Delete"
                    disabled={deleteMutation.isPending}
                    onClick={() => {
                      if (window.confirm(`Delete "${content.title}"?`)) deleteMutation.mutate(content.id)
                    }}
                  ><Trash2 size={17} /></button>
                </div>
              </article>
            ))}
            {contentQuery.data?.length === 0 && <p className="empty-state">No content entries yet.</p>}
          </div>
        )}
      </section>
    </>
  )
}
