import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import axios from 'axios'
import FeedbackModal from './FeedbackModal'
import './App.css'

// Use environment variable for API base URL, fallback to relative path for Vercel
// When deployed on Vercel with API in same project, use relative path
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const DEFAULT_DATASET_ID = 'innova'
const DEFAULT_FOLDERNAME = 'default'

// Custom cell renderer for reasoning column with read more/less
const ReasoningCellRenderer = ({ value }) => {
  const [expanded, setExpanded] = useState(false)
  
  if (!value || value.trim() === '') {
    return <span></span>
  }
  
  const words = value.trim().split(/\s+/)
  const previewWords = words.slice(0, 3).join(' ')
  const shouldTruncate = words.length > 3
  
  return (
    <div style={{ padding: '4px 0' }}>
      {expanded || !shouldTruncate ? (
        <div>
          <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.4, marginBottom: '4px' }}>
            {value}
          </div>
          {shouldTruncate && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                setExpanded(false)
              }}
              style={{
                background: 'none',
                border: 'none',
                color: '#0066cc',
                cursor: 'pointer',
                textDecoration: 'underline',
                fontSize: '12px',
                padding: 0
              }}
            >
              Read less
            </button>
          )}
        </div>
      ) : (
        <div>
          <span>{previewWords}...</span>
          <button
            onClick={(e) => {
              e.stopPropagation()
              setExpanded(true)
            }}
            style={{
              background: 'none',
              border: 'none',
              color: '#0066cc',
              cursor: 'pointer',
              textDecoration: 'underline',
              fontSize: '12px',
              padding: 0,
              marginLeft: '4px'
            }}
          >
            Read more
          </button>
        </div>
      )}
    </div>
  )
}

// CSV file path - will be loaded from public folder
function App() {
  const gridApiRef = useRef(null)
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [feedbackModal, setFeedbackModal] = useState(null)
  const [selectedRows, setSelectedRows] = useState([])
  const [feedbackItems, setFeedbackItems] = useState([])
  const [loadingFeedback, setLoadingFeedback] = useState(false)
  const [expandedFeedbackIds, setExpandedFeedbackIds] = useState(new Set())
  const [submittingFeedback, setSubmittingFeedback] = useState(false)

  // Parse a single CSV line handling quoted fields
  const parseCSVLine = useCallback((line) => {
    const result = []
    let current = ''
    let inQuotes = false
    
    for (let i = 0; i < line.length; i++) {
      const char = line[i]
      const nextChar = line[i + 1]
      
      if (char === '"') {
        if (inQuotes && nextChar === '"') {
          // Escaped quote
          current += '"'
          i++
        } else {
          // Toggle quote state
          inQuotes = !inQuotes
        }
      } else if (char === ',' && !inQuotes) {
        // Field separator
        result.push(current.trim())
        current = ''
      } else {
        current += char
      }
    }
    
    // Add last field
    result.push(current.trim())
    return result
  }, [])

  // Parse CSV helper function
  const parseCSV = useCallback((csvText) => {
    const lines = csvText.split('\n').filter(line => line.trim())
    if (lines.length === 0) return []
    
    // Parse header
    const headers = parseCSVLine(lines[0])
    
    // Parse data rows
    const rows = []
    for (let i = 1; i < lines.length; i++) {
      const values = parseCSVLine(lines[i])
      if (values.length === 0) continue
      
      const row = {}
      headers.forEach((header, idx) => {
        row[header] = values[idx] || ''
      })
      row.row_index = i - 1 // 0-based index
      rows.push(row)
    }
    
    return rows
  }, [parseCSVLine])

  // Load feedback items
  const loadFeedback = useCallback(async () => {
    setLoadingFeedback(true)
    try {
      console.log(`Loading feedback for dataset_id: ${DEFAULT_DATASET_ID}`)
      const response = await axios.get(`${API_BASE}/feedback`, {
        params: {
          dataset_id: DEFAULT_DATASET_ID,
          limit: 100
        }
      })
      const items = response.data.items || []
      console.log(`Loaded ${items.length} feedback items from API:`, items.map(item => ({
        id: item.id,
        row_index: item.row_index,
        status: item.status
      })))
      
      // Fetch detailed information for each feedback item
      const detailedItems = await Promise.all(
        items.map(async (item) => {
          try {
            const detailResponse = await axios.get(`${API_BASE}/feedback/${item.id}`)
            return detailResponse.data
    } catch (err) {
            // If detail fetch fails, use the list item data
            console.warn(`Failed to fetch details for feedback ${item.id}, using list data:`, err)
            return item
          }
        })
      )
      
      console.log(`Displaying ${detailedItems.length} feedback items in UI`)
      setFeedbackItems(detailedItems)
    } catch (err) {
      // Don't show error for feedback loading, it's optional
      console.error('Failed to load feedback:', err)
    } finally {
      setLoadingFeedback(false)
    }
  }, [])

  // Load transactions from API on component mount
  useEffect(() => {
    const loadTransactions = async () => {
      setLoading(true)
      try {
        // Load transactions from API with pagination
        let allRows = []
        let page = 1
        const limit = 200 // Load in chunks
        
        while (true) {
          const response = await axios.get(`${API_BASE}/transactions`, {
            params: {
              dataset_id: DEFAULT_DATASET_ID,
              foldername: DEFAULT_FOLDERNAME,
              page: page,
              limit: limit
            }
          })
          
          const transactions = response.data.rows || []
          if (transactions.length === 0) break
          
          allRows = allRows.concat(transactions)
          
          // If we got fewer items than the limit, we've reached the end
          if (transactions.length < limit) break
          page++
        }
        
        setResults(allRows)
      } catch (err) {
        const errorMsg = err.response?.data?.detail || err.message
        setError(`Failed to load transactions: ${errorMsg}. Make sure the backend is deployed and VITE_API_BASE_URL is set correctly.`)
        console.error('Transaction loading error:', err)
        console.error('API_BASE:', API_BASE)
      } finally {
        setLoading(false)
      }
    }

    loadTransactions()
  }, [])

  // Load feedback on component mount
  useEffect(() => {
    loadFeedback()
  }, [loadFeedback])

  // Update rows when applied feedback is loaded
  useEffect(() => {
    const updateRowsFromAppliedFeedback = async () => {
      if (feedbackItems.length === 0 || results.length === 0) return
      
      // Find all applied feedback items
      const appliedFeedback = feedbackItems.filter(fb => fb.status === 'applied')
      
      if (appliedFeedback.length === 0) return
      
      try {
        // Fetch preview for each applied feedback and update rows
        for (const feedback of appliedFeedback) {
          try {
            const previewResponse = await axios.get(`${API_BASE}/feedback/${feedback.id}/preview`, {
              headers: {
                'accept': 'application/json'
              }
            })
            
            const previewData = previewResponse.data
            const updatedRows = previewData.rows || []
            
            if (updatedRows.length > 0) {
              setResults(prevResults => {
                const updatedResults = [...prevResults]
                
                // Map preview rows to results by row_idx
                updatedRows.forEach(previewRow => {
                  const rowIdx = previewRow.row_idx
                  if (rowIdx !== undefined && rowIdx < updatedResults.length) {
                    // Update L1, L2, L3, L4, L5 from preview data
                    if (previewRow.L1 !== null && previewRow.L1 !== undefined) {
                      updatedResults[rowIdx].L1 = previewRow.L1
                    }
                    if (previewRow.L2 !== null && previewRow.L2 !== undefined) {
                      updatedResults[rowIdx].L2 = previewRow.L2
                    }
                    if (previewRow.L3 !== null && previewRow.L3 !== undefined) {
                      updatedResults[rowIdx].L3 = previewRow.L3
                    }
                    if (previewRow.L4 !== null && previewRow.L4 !== undefined) {
                      updatedResults[rowIdx].L4 = previewRow.L4
                    }
                    if (previewRow.L5 !== null && previewRow.L5 !== undefined) {
                      updatedResults[rowIdx].L5 = previewRow.L5
                    }
                    
                    // Update override_rule_applied if present
                    if (previewRow.override_rule_applied !== null && previewRow.override_rule_applied !== undefined) {
                      updatedResults[rowIdx].override_rule_applied = previewRow.override_rule_applied
                    }
                  }
                })
                
                return updatedResults
              })
            }
    } catch (err) {
            console.warn(`Failed to fetch preview for feedback ${feedback.id}:`, err)
          }
        }
        
        // Refresh grid after all updates
        setTimeout(() => {
          if (gridApiRef.current && !gridApiRef.current.isDestroyed?.()) {
            try {
              gridApiRef.current.refreshCells({ force: true })
            } catch (err) {
              console.warn('Failed to refresh grid:', err)
            }
          }
        }, 100)
      } catch (err) {
        console.warn('Failed to update rows from applied feedback:', err)
      }
    }
    
    updateRowsFromAppliedFeedback()
  }, [feedbackItems, results.length])


  const handleOpenFeedback = () => {
    if (selectedRows.length === 0) {
      setError('Please select a row to provide feedback')
      return
    }
    // Only use the first selected row (single selection)
    setFeedbackModal({
      rows: [selectedRows[0]],
      filename: 'classified.csv',
      iteration: 0,
    })
  }

  const handleSubmitFeedback = async (feedbackItems) => {
    setSubmittingFeedback(true)
    setError(null)
    
    // Close modal immediately for better UX
      setFeedbackModal(null)
      setSelectedRows([])
    
    // Show immediate feedback
    setSuccess(`Submitting feedback for ${feedbackItems.length} item(s)...`)
    
    // Submit in background
    try {
      console.log(`Submitting feedback for ${feedbackItems.length} items:`, feedbackItems.map(item => ({
        row_index: item.row_index,
        corrected_path: item.corrected_path,
        feedback_text: item.feedback_text?.substring(0, 50) + '...'
      })))
      
      // Validate and truncate corrected_path to max 4 levels before submitting
      const validatedItems = feedbackItems.map(item => {
        let correctedPath = item.corrected_path || ''
        if (correctedPath) {
          const parts = correctedPath.split('|').map(p => p.trim()).filter(p => p)
          if (parts.length > 4) {
            correctedPath = parts.slice(0, 4).join('|')
          }
        }
        return {
          ...item,
          corrected_path: correctedPath
        }
      })
      
      // Make POST API call for each feedback item
      // Use Promise.allSettled to ensure all requests are attempted even if some fail
      const promises = validatedItems.map((item, idx) => {
        const payload = {
          dataset_id: DEFAULT_DATASET_ID,
          foldername: DEFAULT_FOLDERNAME,
          row_index: item.row_index,
          corrected_path: item.corrected_path || '',
          feedback_text: item.feedback_text || '',
        }
        console.log(`Submitting feedback ${idx + 1}/${validatedItems.length} for row_index ${item.row_index}:`, payload)
        return axios.post(`${API_BASE}/feedback`, payload, {
          headers: {
            'accept': 'application/json',
            'Content-Type': 'application/json'
          }
        })
      })
      
      const results = await Promise.allSettled(promises)
      const successful = results.filter(r => r.status === 'fulfilled').length
      const failed = results.filter(r => r.status === 'rejected').length
      
      console.log(`Feedback submission results: ${successful} succeeded, ${failed} failed`)
      
      // Log any failures
      results.forEach((result, idx) => {
        if (result.status === 'rejected') {
          console.error(`Failed to submit feedback for row_index ${validatedItems[idx].row_index}:`, result.reason)
        } else {
          console.log(`Successfully submitted feedback for row_index ${validatedItems[idx].row_index}:`, result.value.data)
        }
      })
      
      if (successful > 0) {
        setSuccess(`✅ Feedback submitted successfully! ${successful} item(s) saved.${failed > 0 ? ` ${failed} item(s) failed.` : ''}`)
        
        // Reload feedback list after submission
        loadFeedback()
      
      setTimeout(() => setSuccess(null), 5000)
      }
      
      if (failed > 0) {
        const errorMessages = results
          .filter(r => r.status === 'rejected')
          .map(r => r.reason.response?.data?.detail || r.reason.message)
          .join('; ')
        setError(`Failed to submit ${failed} feedback item(s): ${errorMessages}`)
      }
    } catch (err) {
      if (err.code === 'ERR_NETWORK' || err.message.includes('ERR_CONNECTION_REFUSED')) {
        setError(`Cannot connect to API at ${API_BASE}. Please ensure the backend is running on port 8000.`)
      } else {
        setError(`Failed to submit feedback: ${err.response?.data?.detail || err.message}`)
      }
    } finally {
      setSubmittingFeedback(false)
    }
  }

  const handleApproveFeedback = async (feedbackId, e) => {
    e.stopPropagation() // Prevent expanding/collapsing the card
    try {
      setLoading(true)
      setError(null)
      
      await axios.post(`${API_BASE}/feedback/${feedbackId}/approve`, {
        edited_text: ''
      }, {
        headers: {
          'accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      
      setSuccess(`Feedback #${feedbackId} approved successfully!`)
      
      // Reload feedback list after approval
      loadFeedback()
      
        setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(`Failed to approve feedback: ${err.response?.data?.detail || err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleApplyFeedback = async (feedbackId, rowIndex, e) => {
    e.stopPropagation() // Prevent expanding/collapsing the card
    try {
      setLoading(true)
    setError(null)
      
      // Apply the feedback
      await axios.post(`${API_BASE}/feedback/${feedbackId}/apply`, {
        row_indices: [rowIndex]
      }, {
        headers: {
          'accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      
      // Fetch preview data to get updated rows
      try {
        const previewResponse = await axios.get(`${API_BASE}/feedback/${feedbackId}/preview`, {
          headers: {
            'accept': 'application/json'
          }
        })
        
        const previewData = previewResponse.data
        const updatedRows = previewData.rows || []
        
        // Update the results with preview data
        if (updatedRows.length > 0) {
          setResults(prevResults => {
            const updatedResults = [...prevResults]
            
            // Map preview rows to results by row_idx
            updatedRows.forEach(previewRow => {
              const rowIdx = previewRow.row_idx
              if (rowIdx !== undefined && rowIdx < updatedResults.length) {
                // Update L1, L2, L3, L4, L5 from preview data
                if (previewRow.L1 !== null && previewRow.L1 !== undefined) {
                  updatedResults[rowIdx].L1 = previewRow.L1
                }
                if (previewRow.L2 !== null && previewRow.L2 !== undefined) {
                  updatedResults[rowIdx].L2 = previewRow.L2
                }
                if (previewRow.L3 !== null && previewRow.L3 !== undefined) {
                  updatedResults[rowIdx].L3 = previewRow.L3
                }
                if (previewRow.L4 !== null && previewRow.L4 !== undefined) {
                  updatedResults[rowIdx].L4 = previewRow.L4
                }
                if (previewRow.L5 !== null && previewRow.L5 !== undefined) {
                  updatedResults[rowIdx].L5 = previewRow.L5
                }
                
                // Update override_rule_applied if present
                if (previewRow.override_rule_applied !== null && previewRow.override_rule_applied !== undefined) {
                  updatedResults[rowIdx].override_rule_applied = previewRow.override_rule_applied
                }
              }
            })
            
            return updatedResults
          })
          
          // Refresh the grid to show updated data
          if (gridApiRef.current && !gridApiRef.current.isDestroyed?.()) {
            try {
              gridApiRef.current.refreshCells({ force: true })
            } catch (err) {
              console.warn('Failed to refresh grid:', err)
            }
          }
        }
      } catch (previewErr) {
        console.warn('Failed to fetch preview data, but feedback was applied:', previewErr)
      }
      
      setSuccess(`Feedback #${feedbackId} applied successfully! Rows updated.`)
      
      // Reload feedback list after applying
      loadFeedback()
      
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(`Failed to apply feedback: ${err.response?.data?.detail || err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteFeedback = async (feedbackId, e) => {
    e.stopPropagation() // Prevent expanding/collapsing the card
    if (!window.confirm(`Are you sure you want to delete Feedback #${feedbackId}?`)) {
      return
    }

    try {
    setLoading(true)
    setError(null)
      
      await axios.delete(`${API_BASE}/feedback/${feedbackId}`, {
        headers: {
          'accept': 'application/json'
        }
      })
      
      setSuccess(`Feedback #${feedbackId} deleted successfully!`)
      
      // Reload feedback list after deletion
      loadFeedback()
      
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(`Failed to delete feedback: ${err.response?.data?.detail || err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const columnDefs = useMemo(() => {
    if (results.length === 0) return []

    const toHeader = (key) => {
      return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
    }

    const cols = Object.keys(results[0]).map(key => {
      const baseCol = {
        field: key,
        headerName: toHeader(key),
        sortable: true,
        filter: true,
        resizable: true,
        minWidth: 140,
      }

      if (key === 'reasoning') {
        return {
          ...baseCol,
          cellRenderer: ReasoningCellRenderer,
          autoHeight: true,
          wrapText: true,
        }
      }

      return baseCol
    })

    // Add a selection checkbox column for single row selection
    return [
      {
        colId: '__select__',
        headerName: '',
        checkboxSelection: true,
        headerCheckboxSelection: false, // No header checkbox for single selection
        width: 50,
        pinned: 'left',
        resizable: false,
        sortable: false,
        filter: false,
      },
      ...cols,
    ]
  }, [results])

  const defaultColDef = useMemo(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    minWidth: 140,
  }), [])

  const autoSizeColumns = useCallback(() => {
    if (gridApiRef.current && 
        gridApiRef.current.autoSizeAllColumns && 
        !gridApiRef.current.isDestroyed?.()) {
      try {
      gridApiRef.current.autoSizeAllColumns()
      } catch (err) {
        // Grid might be destroyed, ignore the error
        console.warn('Grid autoSize failed:', err)
      }
    }
  }, [])

  useEffect(() => {
    if (results.length > 0) {
      // Allow grid to render before autosizing
      setTimeout(() => autoSizeColumns(), 0)
    }
  }, [results, autoSizeColumns])

  const onGridReady = useCallback((params) => {
    gridApiRef.current = params.api
    autoSizeColumns()
  }, [autoSizeColumns])

  const onFirstDataRendered = useCallback(() => {
    autoSizeColumns()
  }, [autoSizeColumns])

  const onSelectionChanged = useCallback((event) => {
    const selected = event.api.getSelectedRows()
    // Only keep the first selected row (single selection)
    setSelectedRows(selected.length > 0 ? [selected[0]] : [])
  }, [])


  const rowData = useMemo(() => results, [results])

  return (
    <div className="app-container">
      <div className="header">
        <h1>AP Agent - Spend Classification</h1>
        <p>Review results, provide feedback, and improve classification accuracy</p>
      </div>

      {error && (
        <div className="error">
          {error}
          <button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
        </div>
      )}

      {success && (
        <div className="success">
          {success}
          <button onClick={() => setSuccess(null)} style={{ float: 'right', background: 'none', border: 'none', cursor: 'pointer' }}>×</button>
        </div>
      )}

      <div className="controls">
        <div className="control-group">
          <label>📄 File</label>
          <div style={{ 
            padding: '12px 16px', 
            border: '2px solid #e5e7eb', 
            borderRadius: '10px', 
            background: 'linear-gradient(135deg, #ffffff 0%, #f9fafb 100%)', 
            minWidth: 280,
            boxShadow: '0 2px 4px rgba(0, 0, 0, 0.05)'
          }}>
            <div style={{ fontWeight: '700', color: '#1f2937', fontSize: '15px' }}>📊 classified.csv</div>
          </div>
        </div>

        <div className="control-group">
          <label>✅ Selected Row</label>
          <input 
            type="text" 
            value={selectedRows.length > 0 ? `Row ${selectedRows[0].row_index + 1}` : 'None'} 
            readOnly 
            style={{ 
              width: '120px',
              textAlign: 'center',
              fontWeight: '700',
              fontSize: '16px',
              color: selectedRows.length > 0 ? '#667eea' : '#9ca3af'
            }} 
          />
        </div>

        <button 
          className="btn btn-primary" 
          onClick={handleOpenFeedback} 
          disabled={selectedRows.length === 0}
          style={{ marginTop: 'auto' }}
        >
          💬 Provide Feedback
        </button>
      </div>

      <div className="grid-container">
        {loading ? (
          <div className="loading">Loading results...</div>
        ) : results.length === 0 ? (
          <div className="loading">No results loaded. Select a file above.</div>
        ) : (
          <>
            <div style={{ marginBottom: 10, fontSize: 12, color: '#555' }}>
              Showing {results.length} rows
            </div>
            <div className="ag-theme-alpine" style={{ height: '600px', width: '100%' }}>
              <AgGridReact
                rowData={rowData}
                columnDefs={columnDefs}
                defaultColDef={defaultColDef}
                domLayout="normal"
                rowSelection="single"
                rowMultiSelectWithClick={false}
                onGridReady={onGridReady}
                onFirstDataRendered={onFirstDataRendered}
                onSelectionChanged={onSelectionChanged}
                pagination={true}
                paginationPageSize={50}
                suppressRowClickSelection={false}
                enableCellTextSelection={true}
                suppressHorizontalScroll={false}
              />
            </div>
          </>
        )}
      </div>

      {feedbackModal && (
        <FeedbackModal
          modal={feedbackModal}
          onClose={() => setFeedbackModal(null)}
          onSubmit={handleSubmitFeedback}
          isSubmitting={submittingFeedback}
        />
      )}

      {/* Feedback Display Section */}
      <div style={{ 
        marginTop: '40px', 
        borderTop: '3px solid #e5e7eb', 
        paddingTop: '32px',
        background: 'white',
        borderRadius: '16px',
        padding: '32px',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)'
      }}>
        <div style={{ 
          display: 'flex', 
          justifyContent: 'space-between', 
          alignItems: 'center', 
          marginBottom: '24px' 
        }}>
          <h2 style={{ 
            margin: 0, 
            fontSize: '28px',
            fontWeight: '700',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text'
          }}>
            Submitted Feedback
          </h2>
          <button 
            className="btn btn-secondary" 
            onClick={loadFeedback}
            disabled={loadingFeedback}
            style={{ fontSize: '14px', padding: '10px 20px' }}
          >
            {loadingFeedback ? 'Loading...' : '🔄 Refresh'}
          </button>
        </div>

        {loadingFeedback && feedbackItems.length === 0 ? (
          <div className="loading">Loading feedback...</div>
        ) : feedbackItems.length === 0 ? (
          <div style={{ 
            padding: '60px 20px', 
            textAlign: 'center', 
            color: '#9ca3af',
            fontSize: '16px',
            background: 'linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%)',
            borderRadius: '12px',
            border: '2px dashed #e5e7eb'
          }}>
            📝 No feedback submitted yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {feedbackItems.map((feedback) => {
              const isExpanded = expandedFeedbackIds.has(feedback.id)
              const statusColor = {
                pending: '#f59e0b',
                approved: '#10b981',
                applied: '#3b82f6'
              }[feedback.status] || '#6b7280'

              return (
                <div
                  key={feedback.id}
                  style={{
                    border: `2px solid ${isExpanded ? statusColor : '#e5e7eb'}`,
                    borderRadius: '12px',
                    padding: '20px',
                    background: isExpanded 
                      ? `linear-gradient(135deg, ${statusColor}08 0%, ${statusColor}03 100%)`
                      : 'white',
                    cursor: 'pointer',
                    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                    boxShadow: isExpanded 
                      ? `0 8px 24px ${statusColor}20` 
                      : '0 2px 8px rgba(0, 0, 0, 0.05)'
                  }}
                  onMouseEnter={(e) => {
                    if (!isExpanded) {
                      e.currentTarget.style.transform = 'translateY(-2px)'
                      e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.1)'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isExpanded) {
                      e.currentTarget.style.transform = 'translateY(0)'
                      e.currentTarget.style.boxShadow = '0 2px 8px rgba(0, 0, 0, 0.05)'
                    }
                  }}
                  onClick={() => {
                    const newExpanded = new Set(expandedFeedbackIds)
                    if (isExpanded) {
                      newExpanded.delete(feedback.id)
                    } else {
                      newExpanded.add(feedback.id)
                    }
                    setExpandedFeedbackIds(newExpanded)
                  }}
                >
                  {/* Summary/Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
                        <span style={{ 
                          fontWeight: '700', 
                          fontSize: '18px',
                          color: '#1f2937',
                          letterSpacing: '-0.3px'
                        }}>
                          Feedback #{feedback.id}
                        </span>
                        <span style={{
                          padding: '6px 12px',
                          borderRadius: '20px',
                          fontSize: '11px',
                          fontWeight: '700',
                          background: `linear-gradient(135deg, ${statusColor} 0%, ${statusColor}dd 100%)`,
                          color: 'white',
                          textTransform: 'uppercase',
                          letterSpacing: '0.5px',
                          boxShadow: `0 2px 8px ${statusColor}40`
                        }}>
                          {feedback.status?.toUpperCase() || 'UNKNOWN'}
                        </span>
                      </div>
                      <div style={{ 
                        fontSize: '14px', 
                        color: '#6b7280', 
                        marginBottom: '12px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        flexWrap: 'wrap'
                      }}>
                        <span style={{ 
                          background: '#f3f4f6',
                          padding: '4px 10px',
                          borderRadius: '6px',
                          fontWeight: '600',
                          color: '#374151'
                        }}>
                          Row {feedback.row_index}
                        </span>
                        <span style={{ color: '#9ca3af' }}>•</span>
                        <span style={{ color: '#6b7280' }}>Dataset: <strong>{feedback.dataset_id}</strong></span>
                      </div>
                      <div style={{ 
                        fontSize: '14px', 
                        color: '#374151', 
                        marginTop: '12px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px'
                      }}>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: '8px',
                          padding: '8px 12px',
                          background: '#fef2f2',
                          borderRadius: '8px',
                          borderLeft: '3px solid #ef4444'
                        }}>
                          <span style={{ color: '#9ca3af', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Original:</span>
                          <span style={{ color: '#dc2626', fontWeight: '600' }}>{feedback.original_classification || 'N/A'}</span>
                        </div>
                        <div style={{ 
                          display: 'flex', 
                          alignItems: 'center', 
                          gap: '8px',
                          padding: '8px 12px',
                          background: '#f0fdf4',
                          borderRadius: '8px',
                          borderLeft: '3px solid #10b981'
                        }}>
                          <span style={{ color: '#9ca3af', fontWeight: '600', fontSize: '12px', textTransform: 'uppercase' }}>Corrected:</span>
                          <span style={{ color: '#16a34a', fontWeight: '600' }}>{feedback.corrected_classification || 'N/A'}</span>
                        </div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      {feedback.status === 'pending' && (
                        <>
                          <button
                            className="btn btn-success"
                            onClick={(e) => handleApproveFeedback(feedback.id, e)}
                            disabled={loading}
                            style={{ 
                              fontSize: '13px', 
                              padding: '8px 16px',
                              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '8px',
                              cursor: loading ? 'not-allowed' : 'pointer',
                              fontWeight: '600',
                              boxShadow: '0 2px 8px rgba(16, 185, 129, 0.3)',
                              transition: 'all 0.2s'
                            }}
                            onMouseEnter={(e) => {
                              if (!loading) {
                                e.currentTarget.style.transform = 'translateY(-2px)'
                                e.currentTarget.style.boxShadow = '0 4px 12px rgba(16, 185, 129, 0.4)'
                              }
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.transform = 'translateY(0)'
                              e.currentTarget.style.boxShadow = '0 2px 8px rgba(16, 185, 129, 0.3)'
                            }}
                          >
                            {loading ? '⏳ Approving...' : '✓ Approve'}
                          </button>
                          <button
                            onClick={(e) => handleDeleteFeedback(feedback.id, e)}
                            disabled={loading}
                            style={{ 
                              fontSize: '18px', 
                              padding: '8px 12px',
                              background: 'transparent',
                              color: '#dc2626',
                              border: '2px solid #fee2e2',
                              borderRadius: '8px',
                              cursor: loading ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              transition: 'all 0.2s',
                              background: '#fef2f2'
                            }}
                            title="Delete feedback"
                            onMouseEnter={(e) => {
                              if (!loading) {
                                e.currentTarget.style.background = '#fee2e2'
                                e.currentTarget.style.borderColor = '#dc2626'
                                e.currentTarget.style.transform = 'scale(1.1)'
                              }
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = '#fef2f2'
                              e.currentTarget.style.borderColor = '#fee2e2'
                              e.currentTarget.style.transform = 'scale(1)'
                            }}
                          >
                            🗑️
                          </button>
                        </>
                      )}
                      {feedback.status === 'approved' && (
                        <button
                          className="btn btn-primary"
                          onClick={(e) => handleApplyFeedback(feedback.id, feedback.row_index, e)}
                          disabled={loading}
                          style={{ 
                            fontSize: '13px', 
                            padding: '8px 16px',
                            background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '8px',
                            cursor: loading ? 'not-allowed' : 'pointer',
                            fontWeight: '600',
                            boxShadow: '0 2px 8px rgba(59, 130, 246, 0.3)',
                            transition: 'all 0.2s'
                          }}
                          onMouseEnter={(e) => {
                            if (!loading) {
                              e.currentTarget.style.transform = 'translateY(-2px)'
                              e.currentTarget.style.boxShadow = '0 4px 12px rgba(59, 130, 246, 0.4)'
                            }
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.transform = 'translateY(0)'
                            e.currentTarget.style.boxShadow = '0 2px 8px rgba(59, 130, 246, 0.3)'
                          }}
                        >
                          {loading ? '⏳ Applying...' : '🚀 Apply'}
                        </button>
                      )}
                      <div style={{ 
                        fontSize: '20px', 
                        color: statusColor, 
                        marginLeft: '8px',
                        transition: 'transform 0.3s',
                        transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)'
                      }}>
                        ▶
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div style={{ 
                      marginTop: '20px', 
                      paddingTop: '20px', 
                      borderTop: `2px solid ${statusColor}30`,
                      fontSize: '14px',
                      animation: 'fadeIn 0.3s ease-in'
                    }}>
                      {feedback.feedback_text && (
                        <div style={{ marginBottom: '16px' }}>
                          <strong style={{ 
                            color: '#1f2937',
                            fontSize: '13px',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                            display: 'block',
                            marginBottom: '8px'
                          }}>
                            💬 Feedback Text
                          </strong>
                          <div style={{ 
                            marginTop: '4px', 
                            padding: '14px', 
                            background: 'linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%)', 
                            borderRadius: '10px', 
                            whiteSpace: 'pre-wrap',
                            borderLeft: '4px solid #667eea',
                            lineHeight: '1.7',
                            color: '#374151'
                          }}>
                            {feedback.feedback_text}
                          </div>
                        </div>
                      )}

                      {feedback.action_reasoning && (
                        <div style={{ marginBottom: '16px' }}>
                          <strong style={{ 
                            color: '#1f2937',
                            fontSize: '13px',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                            display: 'block',
                            marginBottom: '8px'
                          }}>
                            🧠 Action Reasoning
                          </strong>
                          <div style={{ 
                            marginTop: '4px', 
                            padding: '14px', 
                            background: 'linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%)', 
                            borderRadius: '10px', 
                            whiteSpace: 'pre-wrap', 
                            lineHeight: '1.7',
                            borderLeft: '4px solid #8b5cf6',
                            color: '#374151'
                          }}>
                            {feedback.action_reasoning}
                          </div>
                        </div>
                      )}

                      {feedback.proposal_text && (
                        <div style={{ marginBottom: '16px' }}>
                          <strong style={{ 
                            color: '#1f2937',
                            fontSize: '13px',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                            display: 'block',
                            marginBottom: '8px'
                          }}>
                            📋 Proposal
                          </strong>
                          <div style={{ 
                            marginTop: '4px', 
                            padding: '14px', 
                            background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)', 
                            borderRadius: '10px', 
                            whiteSpace: 'pre-wrap', 
                            lineHeight: '1.7',
                            borderLeft: '4px solid #3b82f6',
                            color: '#1e40af',
                            fontWeight: '500'
                          }}>
                            {feedback.proposal_text}
                          </div>
                        </div>
                      )}

                      {feedback.created_at && (
                        <div style={{ 
                          fontSize: '12px', 
                          color: '#6b7280', 
                          marginTop: '16px',
                          padding: '10px 14px',
                          background: '#f9fafb',
                          borderRadius: '8px',
                          display: 'inline-block'
                        }}>
                          <strong style={{ color: '#4b5563' }}>🕒 Created:</strong> {new Date(feedback.created_at).toLocaleString()}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

    </div>
  )
}

export default App



