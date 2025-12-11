import React, { useState } from 'react'

function FeedbackModal({ modal, onClose, onSubmit }) {
  const [feedbackItems, setFeedbackItems] = useState(() => {
    return modal.rows.map((row, idx) => ({
      transaction_id: row.supplier_name || `row_${idx}`,
      row_index: idx,
      feedback_type: 'correct',
      corrected_l1: row.L1 || '',
      corrected_l2: row.L2 || '',
      corrected_l3: row.L3 || '',
      corrected_l4: row.L4 || '',
      corrected_l5: row.L5 || '',
      comment: '',
    }))
  })

  const updateFeedbackItem = (index, field, value) => {
    const updated = [...feedbackItems]
    updated[index] = { ...updated[index], [field]: value }
    setFeedbackItems(updated)
  }

  const handleSubmit = () => {
    const feedbackData = {
      result_file: modal.filename,
      iteration: modal.iteration,
      feedback_items: feedbackItems,
    }
    onSubmit(feedbackData)
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
                Transaction {idx + 1}: {modal.rows[idx].supplier_name || 'N/A'}
              </h4>
              
              <div className="form-group">
                <label>Feedback Type</label>
                <select
                  value={item.feedback_type}
                  onChange={(e) => updateFeedbackItem(idx, 'feedback_type', e.target.value)}
                >
                  <option value="correct">Correct</option>
                  <option value="incorrect">Incorrect</option>
                  <option value="correction">Correction Needed</option>
                </select>
              </div>

              {item.feedback_type === 'correction' && (
                <>
                  <div className="form-group">
                    <label>Corrected L1</label>
                    <input
                      type="text"
                      value={item.corrected_l1}
                      onChange={(e) => updateFeedbackItem(idx, 'corrected_l1', e.target.value)}
                      placeholder={modal.rows[idx].L1 || 'Enter L1'}
                    />
                  </div>
                  <div className="form-group">
                    <label>Corrected L2</label>
                    <input
                      type="text"
                      value={item.corrected_l2}
                      onChange={(e) => updateFeedbackItem(idx, 'corrected_l2', e.target.value)}
                      placeholder={modal.rows[idx].L2 || 'Enter L2'}
                    />
                  </div>
                  <div className="form-group">
                    <label>Corrected L3</label>
                    <input
                      type="text"
                      value={item.corrected_l3}
                      onChange={(e) => updateFeedbackItem(idx, 'corrected_l3', e.target.value)}
                      placeholder={modal.rows[idx].L3 || 'Enter L3'}
                    />
                  </div>
                  <div className="form-group">
                    <label>Corrected L4</label>
                    <input
                      type="text"
                      value={item.corrected_l4}
                      onChange={(e) => updateFeedbackItem(idx, 'corrected_l4', e.target.value)}
                      placeholder={modal.rows[idx].L4 || 'Enter L4'}
                    />
                  </div>
                  <div className="form-group">
                    <label>Corrected L5</label>
                    <input
                      type="text"
                      value={item.corrected_l5}
                      onChange={(e) => updateFeedbackItem(idx, 'corrected_l5', e.target.value)}
                      placeholder={modal.rows[idx].L5 || 'Enter L5'}
                    />
                  </div>
                </>
              )}

              <div className="form-group">
                <label>Your approach for classification (used to improve the system)</label>
                <textarea
                  value={item.comment}
                  onChange={(e) => updateFeedbackItem(idx, 'comment', e.target.value)}
                  placeholder="Describe how you approached this classification so we can improve the system."
                />
              </div>
            </div>
          ))}
        </div>

        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-primary" onClick={handleSubmit}>
            Submit Feedback
          </button>
        </div>
      </div>
    </div>
  )
}

export default FeedbackModal

