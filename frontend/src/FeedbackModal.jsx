import React, { useState, useEffect } from 'react'
import axios from 'axios'

function FeedbackModal({ modal, onClose, onSubmit }) {
  const [taxonomyStructure, setTaxonomyStructure] = useState({ L1: [], L2: {}, L3: {}, L4: {} })
  const [loadingTaxonomy, setLoadingTaxonomy] = useState(false)
  
  const [feedbackItems, setFeedbackItems] = useState(() => {
    return modal.rows.map((row, idx) => ({
      transaction_id: row.supplier_name || `row_${idx}`,
      row_index: idx,
      feedback_type: 'correction',
      corrected_l1: row.L1 || '',
      corrected_l2: row.L2 || '',
      corrected_l3: row.L3 || '',
      corrected_l4: row.L4 || '',
      corrected_l5: row.L5 || '',
      comment: '',
    }))
  })

  // Load taxonomy structure on mount
  useEffect(() => {
    loadTaxonomyStructure()
  }, [])

  const loadTaxonomyStructure = async () => {
    setLoadingTaxonomy(true)
    try {
      // Try to get taxonomy file from modal or use default
      const taxonomyFile = modal.taxonomyFile || 'FOX_20230816_161348.yaml'
      const response = await axios.get(`/api/taxonomy/${taxonomyFile}/structure`)
      setTaxonomyStructure(response.data.structure || { L1: [], L2: {}, L3: {}, L4: {} })
    } catch (error) {
      console.error('Failed to load taxonomy structure:', error)
      // Continue with empty structure - dropdowns will be empty
    } finally {
      setLoadingTaxonomy(false)
    }
  }

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
                <label>Corrected L1</label>
                <select
                  value={item.corrected_l1}
                  onChange={(e) => {
                    updateFeedbackItem(idx, 'corrected_l1', e.target.value)
                    // Clear dependent levels when L1 changes
                    if (e.target.value !== item.corrected_l1) {
                      updateFeedbackItem(idx, 'corrected_l2', '')
                      updateFeedbackItem(idx, 'corrected_l3', '')
                      updateFeedbackItem(idx, 'corrected_l4', '')
                    }
                  }}
                  style={{ width: '100%', padding: '8px' }}
                  disabled={loadingTaxonomy}
                >
                  <option value="">Select L1...</option>
                  {taxonomyStructure.L1.map((l1) => (
                    <option key={l1} value={l1}>
                      {l1}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Corrected L2</label>
                <select
                  value={item.corrected_l2}
                  onChange={(e) => {
                    updateFeedbackItem(idx, 'corrected_l2', e.target.value)
                    // Clear dependent levels when L2 changes
                    if (e.target.value !== item.corrected_l2) {
                      updateFeedbackItem(idx, 'corrected_l3', '')
                      updateFeedbackItem(idx, 'corrected_l4', '')
                    }
                  }}
                  style={{ width: '100%', padding: '8px' }}
                  disabled={!item.corrected_l1 || loadingTaxonomy}
                >
                  <option value="">Select L2...</option>
                  {item.corrected_l1 && taxonomyStructure.L2[item.corrected_l1]?.map((l2) => (
                    <option key={l2} value={l2}>
                      {l2}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Corrected L3</label>
                <select
                  value={item.corrected_l3}
                  onChange={(e) => {
                    updateFeedbackItem(idx, 'corrected_l3', e.target.value)
                    // Clear L4 when L3 changes
                    if (e.target.value !== item.corrected_l3) {
                      updateFeedbackItem(idx, 'corrected_l4', '')
                    }
                  }}
                  style={{ width: '100%', padding: '8px' }}
                  disabled={!item.corrected_l2 || loadingTaxonomy}
                >
                  <option value="">Select L3...</option>
                  {item.corrected_l1 && item.corrected_l2 && 
                   taxonomyStructure.L3[`${item.corrected_l1}|${item.corrected_l2}`]?.map((l3) => (
                    <option key={l3} value={l3}>
                      {l3}
                    </option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>Corrected L4</label>
                <select
                  value={item.corrected_l4}
                  onChange={(e) => updateFeedbackItem(idx, 'corrected_l4', e.target.value)}
                  style={{ width: '100%', padding: '8px' }}
                  disabled={!item.corrected_l3 || loadingTaxonomy}
                >
                  <option value="">Select L4...</option>
                  {item.corrected_l1 && item.corrected_l2 && item.corrected_l3 && 
                   taxonomyStructure.L4[`${item.corrected_l1}|${item.corrected_l2}|${item.corrected_l3}`]?.map((l4) => (
                    <option key={l4} value={l4}>
                      {l4}
                    </option>
                  ))}
                </select>
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

