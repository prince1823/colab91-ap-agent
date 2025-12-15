import React, { useState } from 'react'

function FeedbackModal({ modal, onClose, onSubmit, isSubmitting }) {
  const [feedbackItems, setFeedbackItems] = useState(() => {
    return modal.rows.map((row, idx) => {
      // Build current path from L1-L4 (max 4 levels as per backend validation)
      const currentPathParts = [
        row.L1,
        row.L2,
        row.L3,
        row.L4
      ].filter(part => part && part.trim())
      const currentPath = currentPathParts.join('|')
      
      return {
        row_index: row.row_index !== undefined ? row.row_index : idx,
        corrected_path: currentPath || '',
        feedback_text: '',
      }
    })
  })

  const validateCorrectedPath = (path) => {
    if (!path || path.trim() === '') return { valid: true, value: path }
    
    const parts = path.split('|').map(p => p.trim()).filter(p => p)
    if (parts.length > 4) {
      // Truncate to first 4 levels
      return { valid: false, value: parts.slice(0, 4).join('|'), warning: 'Path limited to 4 levels maximum' }
    }
    return { valid: true, value: path }
  }

  const updateFeedbackItem = (index, field, value) => {
    const updated = [...feedbackItems]
    if (field === 'corrected_path') {
      const validation = validateCorrectedPath(value)
      updated[index] = { ...updated[index], [field]: validation.value }
      // Store warning if needed (could be displayed to user)
      if (!validation.valid) {
        console.warn(validation.warning)
      }
    } else {
      updated[index] = { ...updated[index], [field]: value }
    }
    setFeedbackItems(updated)
  }

  const handleSubmit = () => {
    // Validate all corrected_paths before submitting
    const validatedItems = feedbackItems.map(item => {
      const validation = validateCorrectedPath(item.corrected_path)
      return {
        ...item,
        corrected_path: validation.value
      }
    })
    onSubmit(validatedItems)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Provide Feedback ({feedbackItems.length} items)</h2>
        
        <div style={{ maxHeight: '400px', overflowY: 'auto', marginBottom: '20px' }}>
          {feedbackItems.map((item, idx) => (
            <div key={idx} style={{ 
              border: '1px solid #ddd', 
              borderRadius: '6px', 
              padding: '15px', 
              marginBottom: '15px',
              background: '#f9f9f9'
            }}>
              <h4 style={{ margin: '0 0 10px 0', color: '#333' }}>
                Row {idx + 1} (Index: {item.row_index}): {modal.rows[idx].supplier_name || 'N/A'}
              </h4>
              
              <div className="form-group">
                <label>Current Classification Path</label>
                <div style={{ padding: '8px', background: '#f0f0f0', borderRadius: '4px', fontSize: '14px', color: '#666' }}>
                  {(() => {
                    const pathParts = [
                      modal.rows[idx].L1,
                      modal.rows[idx].L2,
                      modal.rows[idx].L3,
                      modal.rows[idx].L4
                    ].filter(part => part && part.trim())
                    return pathParts.length > 0 ? pathParts.join('|') : 'No classification'
                  })()}
                </div>
              </div>
              
              <div className="form-group">
                <label>Corrected Path <span style={{ color: '#666', fontSize: '12px' }}>(e.g., "clinical|clinical supplies", max 4 levels)</span></label>
                <input
                  type="text"
                  value={item.corrected_path}
                  onChange={(e) => updateFeedbackItem(idx, 'corrected_path', e.target.value)}
                  placeholder="Enter corrected path separated by | (max 4 levels)"
                  style={{ width: '100%' }}
                />
                {item.corrected_path && item.corrected_path.split('|').filter(p => p.trim()).length > 4 && (
                  <div style={{ color: '#f59e0b', fontSize: '12px', marginTop: '4px' }}>
                    ⚠️ Path will be limited to first 4 levels
                  </div>
                )}
              </div>

              <div className="form-group">
                <label>Feedback Text</label>
                <textarea
                  value={item.feedback_text}
                  onChange={(e) => updateFeedbackItem(idx, 'feedback_text', e.target.value)}
                  placeholder="Enter your feedback"
                  rows={3}
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          ))}
        </div>

        <div className="modal-actions">
          <button 
            className="btn btn-secondary" 
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button 
            className="btn btn-primary" 
            onClick={handleSubmit}
            disabled={isSubmitting}
            style={{ 
              position: 'relative',
              opacity: isSubmitting ? 0.7 : 1,
              cursor: isSubmitting ? 'not-allowed' : 'pointer'
            }}
          >
            {isSubmitting ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ 
                  display: 'inline-block',
                  width: '14px',
                  height: '14px',
                  border: '2px solid #ffffff',
                  borderTopColor: 'transparent',
                  borderRadius: '50%',
                  animation: 'spin 0.6s linear infinite'
                }}></span>
                Submitting...
              </span>
            ) : (
              'Submit Feedback'
            )}
          </button>
        </div>
        {isSubmitting && (
          <div style={{
            marginTop: '15px',
            padding: '12px',
            background: '#f0f9ff',
            borderRadius: '6px',
            border: '1px solid #bae6fd',
            fontSize: '14px',
            color: '#0369a1',
            display: 'flex',
            alignItems: 'center',
            gap: '10px'
          }}>
            <span style={{
              display: 'inline-block',
              width: '16px',
              height: '16px',
              border: '2px solid #0369a1',
              borderTopColor: 'transparent',
              borderRadius: '50%',
              animation: 'spin 0.6s linear infinite'
            }}></span>
            Submitting feedback for {feedbackItems.length} item{feedbackItems.length !== 1 ? 's' : ''}...
          </div>
        )}
      </div>
    </div>
  )
}

export default FeedbackModal

