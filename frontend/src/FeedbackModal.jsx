import React, { useState } from 'react'

function FeedbackModal({ modal, onClose, onSubmit }) {
  const [feedbackItems, setFeedbackItems] = useState(() => {
    return modal.rows.map((row, idx) => ({
      transaction_id: row.supplier_name || `row_${idx}`,
      row_index: idx,
      feedback_type: 'correction', // free text
      corrected_l1: row.L1 || '',
      corrected_l2: row.L2 || '',
      corrected_l3: row.L3 || '',
      corrected_l4: row.L4 || '',
      corrected_l5: row.L5 || '',
      comment: '',
      rating: '',
    }))
  })
  const [userNotes, setUserNotes] = useState('')

  const updateFeedbackItem = (index, field, value) => {
    const updated = [...feedbackItems]
    updated[index] = { ...updated[index], [field]: value }
    setFeedbackItems(updated)
  }

  const handleSubmit = () => {
    const normalizedItems = feedbackItems.map((item) => {
      const parsedRating =
        item.rating === '' || item.rating === null || item.rating === undefined
          ? undefined
          : Number(item.rating)
      return {
        ...item,
        rating: Number.isFinite(parsedRating) ? parsedRating : undefined,
      }
    })

    const feedbackData = {
      result_file: modal.filename,
      iteration: modal.iteration,
      feedback_items: normalizedItems,
      user_notes: userNotes || undefined,
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
                <label>Corrected L1</label>
                <input
                  type="text"
                  value={item.corrected_l1}
                  onChange={(e) => updateFeedbackItem(idx, 'corrected_l1', e.target.value)}
                  placeholder="Enter L1"
                />
              </div>
              <div className="form-group">
                <label>Corrected L2</label>
                <input
                  type="text"
                  value={item.corrected_l2}
                  onChange={(e) => updateFeedbackItem(idx, 'corrected_l2', e.target.value)}
                  placeholder="Enter L2"
                />
              </div>
              <div className="form-group">
                <label>Corrected L3</label>
                <input
                  type="text"
                  value={item.corrected_l3}
                  onChange={(e) => updateFeedbackItem(idx, 'corrected_l3', e.target.value)}
                  placeholder="Enter L3"
                />
              </div>
              <div className="form-group">
                <label>Corrected L4</label>
                <input
                  type="text"
                  value={item.corrected_l4}
                  onChange={(e) => updateFeedbackItem(idx, 'corrected_l4', e.target.value)}
                  placeholder="Enter L4"
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

              <div className="form-group">
                <label>Feedback Type</label>
                <input
                  type="text"
                  value={item.feedback_type}
                  onChange={(e) => updateFeedbackItem(idx, 'feedback_type', e.target.value)}
                  placeholder="correction / correct / incorrect"
                />
              </div>

              <div className="form-group">
                <label>Rating (1-5)</label>
                <input
                  type="number"
                  min="1"
                  max="5"
                  value={item.rating}
                  onChange={(e) => updateFeedbackItem(idx, 'rating', e.target.value)}
                  placeholder="Optional"
                />
              </div>

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

        <div className="form-group" style={{ marginTop: 12 }}>
          <label>User notes (optional)</label>
          <textarea
            value={userNotes}
            onChange={(e) => setUserNotes(e.target.value)}
            placeholder="Any additional context for this feedback batch"
          />
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

