import React, { useState } from 'react'

function ProposalModal({ proposal, onClose, onApprove, onReject, loading = false }) {
  const [editedText, setEditedText] = useState(proposal.proposed_change || '')
  const [validationErrors, setValidationErrors] = useState([])

  const handleApprove = () => {
    // Basic validation
    const errors = []
    if (!editedText.trim()) {
      errors.push('Proposed change text cannot be empty')
    }
    
    setValidationErrors(errors)
    if (errors.length === 0) {
      onApprove(editedText)
    }
  }

  const getActionTypeLabel = (type) => {
    const labels = {
      taxonomy_update: 'Taxonomy Update',
      user_context_update: 'User Context Update',
      supplier_db_update: 'Supplier Database Update',
      rule_creation: 'Rule Creation',
    }
    return labels[type] || type
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal proposal-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Review Proposed Change</h2>
        
        <div className="proposal-info">
          <div className="proposal-field">
            <label>Action Type:</label>
            <span className="action-type-badge">{getActionTypeLabel(proposal.action_type)}</span>
          </div>
          
          <div className="proposal-field">
            <label>Description:</label>
            <p className="proposal-description">{proposal.description}</p>
          </div>
        </div>

        <div className="proposal-field">
          <label>Proposed Change (You can edit this text):</label>
          <textarea
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            rows={8}
            className="proposal-textarea"
            placeholder="Enter proposed change..."
          />
        </div>

        {validationErrors.length > 0 && (
          <div className="error" style={{ marginTop: '10px' }}>
            {validationErrors.map((error, idx) => (
              <div key={idx}>{error}</div>
            ))}
          </div>
        )}

        <div className="modal-actions">
          <button 
            className="btn btn-secondary" 
            onClick={onReject}
            disabled={loading}
          >
            Reject
          </button>
          <button 
            className="btn btn-primary" 
            onClick={handleApprove}
            disabled={loading}
          >
            {loading ? 'Processing...' : 'Approve'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ProposalModal
