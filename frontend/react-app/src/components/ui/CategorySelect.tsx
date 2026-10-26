import { Check, ChevronDown } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'
import { useChatStore } from '../../store/chatStore'

const OPTIONS: { value: string | null; label: string }[] = [
  { value: null, label: '全部' },
  { value: '人物', label: '人物' },
  { value: '心相', label: '心相' },
  { value: '剧情', label: '剧情' },
  { value: '世界', label: '世界' },
  { value: '阵营', label: '阵营' },
  { value: '日历', label: '日历' },
]

export function CategorySelect() {
  const category = useChatStore((s) => s.category)
  const setCategory = useChatStore((s) => s.setCategory)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listRef = useRef<HTMLUListElement>(null)
  const triggerId = useId()
  const listboxId = useId()
  const selectedIndex = Math.max(0, OPTIONS.findIndex((option) => option.value === category))
  const selectedOption = OPTIONS[selectedIndex]

  const openMenu = () => {
    setActiveIndex(selectedIndex)
    setOpen(true)
  }

  const selectOption = (index: number) => {
    setCategory(OPTIONS[index].value)
    setOpen(false)
    triggerRef.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    const list = listRef.current
    list?.focus()
    const activeOption = list?.children[activeIndex] as HTMLElement | undefined
    if (!list || !activeOption) return

    const optionTop = activeOption.offsetTop
    const optionBottom = optionTop + activeOption.offsetHeight
    if (optionTop < list.scrollTop) list.scrollTop = optionTop
    else if (optionBottom > list.scrollTop + list.clientHeight) {
      list.scrollTop = Math.max(0, optionBottom - list.clientHeight)
    }
  }, [open, activeIndex])

  useEffect(() => {
    if (!open) return
    const closeOnOutsidePointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsidePointer)
    return () => document.removeEventListener('pointerdown', closeOnOutsidePointer)
  }, [open])

  const onTriggerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    event.preventDefault()
    openMenu()
  }

  const onListKeyDown = (event: React.KeyboardEvent<HTMLUListElement>) => {
    if (event.key === 'Tab') {
      setOpen(false)
      return
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      setOpen(false)
      triggerRef.current?.focus()
      return
    }
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      selectOption(activeIndex)
      return
    }

    let nextIndex: number | undefined
    if (event.key === 'ArrowDown') nextIndex = (activeIndex + 1) % OPTIONS.length
    else if (event.key === 'ArrowUp') nextIndex = (activeIndex - 1 + OPTIONS.length) % OPTIONS.length
    else if (event.key === 'Home') nextIndex = 0
    else if (event.key === 'End') nextIndex = OPTIONS.length - 1
    if (nextIndex === undefined) return
    event.preventDefault()
    setActiveIndex(nextIndex)
  }

  return (
    <div ref={rootRef} className="category-select">
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        role="combobox"
        aria-label="检索范围"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-haspopup="listbox"
        className="category-select__trigger"
        onClick={() => open ? setOpen(false) : openMenu()}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="category-select__value">{selectedOption.label}</span>
        <ChevronDown aria-hidden="true" className="category-select__chevron" />
      </button>
      {open && (
        <ul
          ref={listRef}
          id={listboxId}
          role="listbox"
          aria-labelledby={triggerId}
          aria-activedescendant={`${listboxId}-option-${activeIndex}`}
          data-page-wheel-lock="true"
          tabIndex={0}
          className="category-select__menu"
          onKeyDown={onListKeyDown}
        >
          {OPTIONS.map((option, index) => {
            const selected = option.value === category
            return (
              <li
                key={option.label}
                id={`${listboxId}-option-${index}`}
                role="option"
                aria-selected={selected}
                data-active={activeIndex === index || undefined}
                className="category-select__option"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => selectOption(index)}
              >
                <span>{option.label}</span>
                {selected && <Check aria-hidden="true" className="category-select__option-check" />}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
