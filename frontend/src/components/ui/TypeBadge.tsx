import React from 'react'
import { getTypeColor, getTypeTextColor, isValidType } from '../../design-system/type-colors'

interface TypeBadgeProps {
  type: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizeClasses = {
  sm: 'px-2 py-0.5 text-[9px]',
  md: 'px-3 py-1 text-[10px]',
  lg: 'px-4 py-1.5 text-xs',
}

const TypeBadge: React.FC<TypeBadgeProps> = ({ type, size = 'md', className = '' }) => {
  const normalizedType = type.toLowerCase()
  const bgColor = getTypeColor(normalizedType)
  const textColor = getTypeTextColor(normalizedType)

  return (
    <span
      className={`inline-flex items-center justify-center rounded-full font-pixel uppercase tracking-wider font-semibold ${sizeClasses[size]} ${className}`}
      style={{ backgroundColor: bgColor, color: textColor }}
      data-type={normalizedType}
      aria-label={`Type: ${normalizedType}`}
    >
      {normalizedType}
    </span>
  )
}

export default TypeBadge
