import React from 'react'
import { motion } from 'framer-motion'

interface StreamingCursorProps {
  isStreaming?: boolean
  className?: string
}

const StreamingCursor: React.FC<StreamingCursorProps> = ({ isStreaming = true, className = '' }) => {
  if (!isStreaming) return null

  return (
    <motion.span
      className={`inline-block ml-0.5 align-middle text-current ${className}`}
      animate={{ opacity: [1, 0, 1] }}
      transition={{ duration: 1, repeat: Infinity, ease: 'steps(1)' }}
      aria-hidden="true"
    >
      |
    </motion.span>
  )
}

export default StreamingCursor
