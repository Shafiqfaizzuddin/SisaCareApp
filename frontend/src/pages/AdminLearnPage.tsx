import { useEffect, useState, type FormEvent } from 'react'
import {
  fetchAdminLearnArticles, removeLearnImage, saveLearnArticle, uploadLearnImage,
  type LearnArticle, type LearnArticleInput,
} from '../features/education/education-api'

const emptyForm: LearnArticleInput = {
  title: '', summary: '', body: '', image_alt: '', published: true, sort_order: 0,
}

export function AdminLearnPage() {
  const [articles, setArticles] = useState<LearnArticle[]>([])
  const [form, setForm] = useState<LearnArticleInput>(emptyForm)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [image, setImage] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let active = true
    void fetchAdminLearnArticles().then(value => { if (active) setArticles(value) })
      .catch(value => { if (active) setError(value instanceof Error ? value.message : 'Could not load learning content.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!image) { setPreviewUrl(null); return }
    const url = URL.createObjectURL(image)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [image])

  function edit(article: LearnArticle) {
    setEditingId(article.id)
    setForm({ title: article.title, summary: article.summary, body: article.body,
      image_alt: article.image_alt, published: article.published, sort_order: article.sort_order })
    setImage(null)
    setError('')
    setNotice('')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function reset() {
    setEditingId(null)
    setForm(emptyForm)
    setImage(null)
  }

  async function reload() {
    setArticles(await fetchAdminLearnArticles())
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    if (image && (!['image/jpeg', 'image/png', 'image/webp'].includes(image.type) || image.size > 5 * 1024 * 1024)) {
      setError('Choose a JPG, PNG or WEBP image of at most 5 MB.')
      return
    }
    if (image && !form.image_alt.trim()) {
      setError('Describe the image for people using screen readers.')
      return
    }
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const saved = await saveLearnArticle(form, editingId ?? undefined)
      setEditingId(saved.id)
      if (image) await uploadLearnImage(saved.id, image)
      await reload()
      setNotice(image ? 'Article and image saved.' : 'Article saved.')
      reset()
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The article could not be saved.')
      // A created article may have been saved before its image failed.
      // Retain its ID and the form so retry updates it rather than duplicating it.
      void reload().catch(() => undefined)
    } finally {
      setBusy(false)
    }
  }

  async function togglePublished(article: LearnArticle) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await saveLearnArticle({ title: article.title, summary: article.summary, body: article.body,
        image_alt: article.image_alt, published: !article.published, sort_order: article.sort_order }, article.id)
      await reload()
      setNotice(article.published ? 'Article hidden from Learn.' : 'Article published on Learn.')
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The article could not be updated.')
    } finally {
      setBusy(false)
    }
  }

  async function removeImage() {
    if (!editingId || busy) return
    setBusy(true)
    setError('')
    try {
      await removeLearnImage(editingId)
      setImage(null)
      await reload()
      setNotice('Image removed from the article. The stored original remains available for audit.')
    } catch (value) {
      setError(value instanceof Error ? value.message : 'The image could not be removed.')
    } finally {
      setBusy(false)
    }
  }

  const selected = articles.find(article => article.id === editingId)
  return <section className="admin-learn-page">
    <header className="admin-page-heading"><div><p className="eyebrow">Public learning content</p><h1>Manage Learn</h1>
      <p>Share practical solid waste and recycling information. Published articles appear on the public Learn page.</p></div></header>
    {loading && <p role="status">Loading articles...</p>}
    {error && <p role="alert" className="validation-error">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <div className="admin-panel">
      <h2>{editingId ? 'Edit article' : 'Create article'}</h2>
      <form className="learn-editor" onSubmit={event => void save(event)}>
        <div className="field"><label htmlFor="learn-title">Title</label><input id="learn-title" required maxLength={160} value={form.title} disabled={busy} onChange={event => setForm(value => ({ ...value, title: event.target.value }))} /></div>
        <div className="field"><label htmlFor="learn-summary">Short introduction</label><textarea id="learn-summary" required maxLength={500} rows={2} value={form.summary} disabled={busy} onChange={event => setForm(value => ({ ...value, summary: event.target.value }))} /></div>
        <div className="field"><label htmlFor="learn-body">Information and guidance</label><textarea id="learn-body" required maxLength={6000} rows={7} value={form.body} disabled={busy} onChange={event => setForm(value => ({ ...value, body: event.target.value }))} /></div>
        <div className="field"><label htmlFor="learn-image">Image (optional)</label><input id="learn-image" type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={event => setImage(event.target.files?.[0] ?? null)} /><span className="field__hint">JPG, PNG or WEBP, up to 5 MB. The image scales to phones and desktops.</span></div>
        {(previewUrl || selected?.image_url) && <div className="learn-editor__preview"><img src={previewUrl || `/api/education/admin/articles/${selected?.id}/image?v=${encodeURIComponent(selected?.updated_at ?? '')}`} alt={form.image_alt || 'Article preview'} /></div>}
        {selected?.image_url && <button type="button" className="button button--secondary learn-editor__remove-image" disabled={busy} onClick={() => void removeImage()}>Remove current image</button>}
        <div className="field"><label htmlFor="learn-alt">Image description</label><input id="learn-alt" maxLength={250} value={form.image_alt} disabled={busy} onChange={event => setForm(value => ({ ...value, image_alt: event.target.value }))} placeholder="Describe what the image shows" /></div>
        <div className="field"><label htmlFor="learn-order">Display order</label><input id="learn-order" type="number" min="0" max="10000" value={form.sort_order} disabled={busy} onChange={event => setForm(value => ({ ...value, sort_order: Number(event.target.value) }))} /></div>
        <label className="checkbox-field"><input type="checkbox" checked={form.published} disabled={busy} onChange={event => setForm(value => ({ ...value, published: event.target.checked }))} /> Published</label>
        <div className="learn-editor__actions"><button className="button button--primary" disabled={busy}>{busy ? 'Saving...' : editingId ? 'Save changes' : 'Publish article'}</button>
          {editingId && <button type="button" className="button button--secondary" disabled={busy} onClick={reset}>Cancel edit</button>}</div>
      </form>
    </div>
    <div className="admin-panel"><h2>Articles</h2>
      {!loading && articles.length === 0 && <p>No articles yet.</p>}
      <ul className="learn-admin-list">{articles.map(article => <li key={article.id} className={article.image_url ? undefined : 'learn-admin-list__text-only'}>
        {article.image_url && <img src={`/api/education/admin/articles/${article.id}/image?v=${encodeURIComponent(article.updated_at)}`} alt={article.image_alt} loading="lazy" />}
        <div><strong>{article.title}</strong><small>{article.published ? 'Published' : 'Hidden'} · Order {article.sort_order}</small><p>{article.summary}</p></div>
        <div className="learn-admin-list__actions"><button type="button" className="button button--secondary" disabled={busy} onClick={() => edit(article)}>Edit</button>
          <button type="button" className="button button--secondary" disabled={busy} onClick={() => void togglePublished(article)}>{article.published ? 'Hide' : 'Publish'}</button></div>
      </li>)}</ul>
    </div>
  </section>
}
