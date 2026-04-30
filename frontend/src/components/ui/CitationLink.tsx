import React, { useState } from 'react'
import { ExternalLink, BookOpen } from 'lucide-react'
import { Citation } from '../../store/sessionStore'

interface CitationLinkProps {
  citation: Citation
  index?: number
  className?: string
}

const CitationLink: React.FC<CitationLinkProps> = ({
  citation,
  index,
  className = '',
}) => {
  const [tooltipVisible, setTooltipVisible] = useState(false)
  const label = index !== undefined ? `[${index + 1}]` : `[Source: ${citation.collection}]`

  return (
    <span className={`relative inline-flex items-center ${className}`}>
      <button
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-bg-panel border border-gray-600 text-pikachu-yellow hover:text-yellow-300 text-xs transition-colors"
        onMouseEnter={() => setTooltipVisible(true)}
        onMouseLeave={() => setTooltipVisible(false)}
        onFocus={() => setTooltipVisible(true)}
        onBlur={() => setTooltipVisible(false)}
        aria-label={`Source: ${citation.collection}`}
        data-document-id={citation.documentId}
      >
        <BookOpen size={11} />
        <span>{label}</span>
      </button>

      {tooltipVisible && (
        <div
          className="absolute bottom-full left-0 mb-2 z-[300] w-72 bg-bg-panel border border-gray-600 rounded-lg p-3 shadow-lg text-xs text-text-light"
          role="tooltip"
        >
          <div className="flex items-center justify-between mb-1">
            <span className="font-semibold text-pikachu-yellow capitalize">
              {citation.collection.replace(/_/g, ' ')}
            </span>
            {citation.sourceUrl && (
              <a
                href={citation.sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 flex items-center gap-0.5"
                aria-label="Open source"
              >
                <ExternalLink size={11} />
              </a>
            )}
          </div>
          <p className="text-gray-300 line-clamp-3 leading-relaxed">{citation.passage}</p>
          <p className="text-gray-500 mt-1 truncate">ID: {citation.documentId}</p>
        </div>
      )}
    </span>
  )
}

export default CitationLink
