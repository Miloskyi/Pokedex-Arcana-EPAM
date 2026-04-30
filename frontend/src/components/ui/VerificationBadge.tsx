import React from 'react'
import { CheckCircle, AlertTriangle, HelpCircle } from 'lucide-react'

interface VerificationBadgeProps {
  verified: boolean
  discrepancyDetected?: boolean
  agentValue?: number | string
  referenceValue?: number | string
  className?: string
}

const VerificationBadge: React.FC<VerificationBadgeProps> = ({
  verified,
  discrepancyDetected = false,
  agentValue,
  referenceValue,
  className = '',
}) => {
  if (discrepancyDetected) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-yellow-400 text-xs font-body ${className}`}
        title={`⚠️ Discrepancy: agent=${agentValue}, reference=${referenceValue}`}
        aria-label="Discrepancy detected"
      >
        <AlertTriangle size={14} className="shrink-0" />
        <span className="hidden sm:inline">Discrepancy</span>
      </span>
    )
  }

  if (verified) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-green-400 text-xs font-body ${className}`}
        title="Verified by Verification Agent"
        aria-label="Verified"
      >
        <CheckCircle size={14} className="shrink-0" />
        <span className="hidden sm:inline">Verified</span>
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1 text-gray-400 text-xs font-body ${className}`}
      title="Not yet verified"
      aria-label="Unverified"
    >
      <HelpCircle size={14} className="shrink-0" />
      <span className="hidden sm:inline">Unverified</span>
    </span>
  )
}

export default VerificationBadge
