import { useEffect } from 'react'

type ModalProps = {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  title?: string
  width?: 'half' | 'full' | 'medium'
  position?: 'right' | 'center'
}

export default function Modal({
  open,
  onClose,
  title,
  children,
  width = 'medium',
  position = 'center',
}: ModalProps) {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    if (open) {
      document.addEventListener('keydown', handleEscape)
      document.body.style.overflow = 'hidden'
    }
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  const widthClass =
    width === 'half'
      ? position === 'right'
        ? 'w-[50vw] min-w-[320px]'
        : 'w-full max-w-[50vw]'
      : width === 'full'
        ? 'w-full max-w-2xl'
        : 'w-full max-w-lg'
  const positionClass =
    position === 'right'
      ? 'fixed top-0 right-0 h-full animate-slide-in-right'
      : 'fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 max-h-[90vh] animate-fade-in'

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        className={`${positionClass} ${widthClass} z-50 flex flex-col rounded-xl border border-slate-200 bg-white shadow-modal ${
          position === 'right' ? 'rounded-l-xl' : ''
        }`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'modal-title' : undefined}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-slate-200 px-5 py-4">
          {title && (
            <h2 id="modal-title" className="text-lg font-semibold text-slate-900">
              {title}
            </h2>
          )}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto rounded-lg p-1.5 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className="flex-1 overflow-auto p-5">{children}</div>
      </div>
    </>
  )
}
