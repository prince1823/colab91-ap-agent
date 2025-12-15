import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import axios from 'axios'
import FeedbackModal from './FeedbackModal'
import './App.css'

const API_BASE = 'http://localhost:8000/api/v1'
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

// Hard-coded CSV file content from classified.csv
const HARD_CODED_CSV = `supplier_name,gl_description,line_description,memo,line_memo,invoice_date,company,creation_date,amount,currency,Cost Center Name,Client Spend Category,Supplier Category,Country,L1,L2,L3,L4,L5,override_rule_applied,reasoning,should_research,prioritization_strategy,supplier_context_strength,transaction_data_quality,prioritization_reasoning,error
kpmg llp,professional fees,"progress billing for professional services rendered pursuant to the engagement letter dated october 13, 2020 in connection with tax compliance services:","progress billing for professional services rendered pursuant to the engagement letter dated october 13, 2020 in connection with tax compliance services:",[blank],2022-02-24,"le0017 innovacare services company, llc",2022-02-24,105000.0,usd,corporate_inno,sc00138 professional services consulting,professional services,united states of america,non clinical,professional services,audit and tax services,audit and tax services,,,"[high] The transaction involves multiple line items primarily related to professional services rendered by KPMG LLP, specifically in the area of tax compliance and consulting. The significant amount of $107,736.00 indicates a major service engagement, aligning with the supplier's profile of providing professional services, particularly in tax and audit. The descriptions of the line items explicitly mention tax consulting services and compliance, which strongly correlate with the taxonomy paths related to audit and tax services. Given the prioritization hint of 'transaction_primary', the focus is on the nature of the services provided rather than the supplier's general profile, leading to a classification that emphasizes the consulting and tax services rendered. [Invoice-level batch processing]",True,transaction_primary,none,rich,"The transaction data provides a clear and specific description of the services rendered, indicating that this is a billing for professional tax consulting services. The amount is substantial, and the invoice date is provided, which adds to the context. However, the supplier profile is not available, which limits the ability to assess the supplier's context. Given that ""kpmg llp"" is a well-known professional services firm, it is likely that research would yield useful information about their services and industry. Therefore, research is warranted to gain a better understanding of the supplier's context. [Invoice-level assessment: 5 line items]",
kpmg llp,accounts payable,"progress billing for professional services rendered pursuant to the engagement letter dated october 13, 2020 in connection with tax compliance services:","progress billing for professional services rendered pursuant to the engagement letter dated october 13, 2020 in connection with tax compliance services:","progress billing for professional services rendered pursuant to the engagement letter dated october 13, 2020 in connection with tax compliance services:",2022-02-24,"le0017 innovacare services company, llc",2022-02-24,0.0,usd,[blank],[blank],professional services,united states of america,non clinical,professional services,audit and tax services,audit and tax services,,,"[high] The transaction involves multiple line items primarily related to professional services rendered by KPMG LLP, specifically in the area of tax compliance and consulting. The significant amount of $107,736.00 indicates a major service engagement, aligning with the supplier's profile of providing professional services, particularly in tax and audit. The descriptions of the line items explicitly mention tax consulting services and compliance, which strongly correlate with the taxonomy paths related to audit and tax services. Given the prioritization hint of 'transaction_primary', the focus is on the nature of the services provided rather than the supplier's general profile, leading to a classification that emphasizes the consulting and tax services rendered. [Invoice-level batch processing]",True,transaction_primary,none,rich,"The transaction data provides a clear and specific description of the services rendered, indicating that this is a billing for professional tax consulting services. The amount is substantial, and the invoice date is provided, which adds to the context. However, the supplier profile is not available, which limits the ability to assess the supplier's context. Given that ""kpmg llp"" is a well-known professional services firm, it is likely that research would yield useful information about their services and industry. Therefore, research is warranted to gain a better understanding of the supplier's context. [Invoice-level assessment: 5 line items]",
kpmg llp,accounts payable,"billing for tax consulting services per the engagement letter dated october 13, 2020.","billing for tax consulting services per the engagement letter dated october 13, 2020.","billing for tax consulting services per the engagement letter dated october 13, 2020.",2022-02-24,"le0017 innovacare services company, llc",2022-02-24,0.0,usd,[blank],[blank],professional services,united states of america,non clinical,professional services,audit and tax services,audit and tax services,,,"[high] The transaction involves multiple line items primarily related to professional services rendered by KPMG LLP, specifically in the area of tax compliance and consulting. The significant amount of $107,736.00 indicates a major service engagement, aligning with the supplier's profile of providing professional services, particularly in tax and audit. The descriptions of the line items explicitly mention tax consulting services and compliance, which strongly correlate with the taxonomy paths related to audit and tax services. Given the prioritization hint of 'transaction_primary', the focus is on the nature of the services provided rather than the supplier's general profile, leading to a classification that emphasizes the consulting and tax services rendered. [Invoice-level batch processing]",True,transaction_primary,none,rich,"The transaction data provides a clear and specific description of the services rendered, indicating that this is a billing for professional tax consulting services. The amount is substantial, and the invoice date is provided, which adds to the context. However, the supplier profile is not available, which limits the ability to assess the supplier's context. Given that ""kpmg llp"" is a well-known professional services firm, it is likely that research would yield useful information about their services and industry. Therefore, research is warranted to gain a better understanding of the supplier's context. [Invoice-level assessment: 5 line items]",
kpmg llp,professional fees,"billing for tax consulting services per the engagement letter dated october 13, 2020.","billing for tax consulting services per the engagement letter dated october 13, 2020.",[blank],2022-02-24,"le0017 innovacare services company, llc",2022-02-24,2736.0,usd,corporate_inno,sc00138 professional services consulting,professional services,united states of america,non clinical,professional services,audit and tax services,audit and tax services,,,"[high] The transaction involves multiple line items primarily related to professional services rendered by KPMG LLP, specifically in the area of tax compliance and consulting. The significant amount of $107,736.00 indicates a major service engagement, aligning with the supplier's profile of providing professional services, particularly in tax and audit. The descriptions of the line items explicitly mention tax consulting services and compliance, which strongly correlate with the taxonomy paths related to audit and tax services. Given the prioritization hint of 'transaction_primary', the focus is on the nature of the services provided rather than the supplier's general profile, leading to a classification that emphasizes the consulting and tax services rendered. [Invoice-level batch processing]",True,transaction_primary,none,rich,"The transaction data provides a clear and specific description of the services rendered, indicating that this is a billing for professional tax consulting services. The amount is substantial, and the invoice date is provided, which adds to the context. However, the supplier profile is not available, which limits the ability to assess the supplier's context. Given that ""kpmg llp"" is a well-known professional services firm, it is likely that research would yield useful information about their services and industry. Therefore, research is warranted to gain a better understanding of the supplier's context. [Invoice-level assessment: 5 line items]",
kpmg llp,accounts payable,"fees for q4 2020 federal tax estimates, pursuant to our engagement letter dated october 13, 2020 and the addendum dated december 11, 2020.","fees for q4 2020 federal tax estimates, pursuant to our engagement letter dated october 13, 2020 and the addendum dated december 11, 2020.","fees for q4 2020 federal tax estimates, pursuant to our engagement letter dated october 13, 2020 and the addendum dated december 11, 2020.",2022-02-24,"le0017 innovacare services company, llc",2022-02-24,0.0,usd,[blank],[blank],professional services,united states of america,non clinical,professional services,audit and tax services,audit and tax services,,,"[high] The transaction involves multiple line items primarily related to professional services rendered by KPMG LLP, specifically in the area of tax compliance and consulting. The significant amount of $107,736.00 indicates a major service engagement, aligning with the supplier's profile of providing professional services, particularly in tax and audit. The descriptions of the line items explicitly mention tax consulting services and compliance, which strongly correlate with the taxonomy paths related to audit and tax services. Given the prioritization hint of 'transaction_primary', the focus is on the nature of the services provided rather than the supplier's general profile, leading to a classification that emphasizes the consulting and tax services rendered. [Invoice-level batch processing]",True,transaction_primary,none,rich,"The transaction data provides a clear and specific description of the services rendered, indicating that this is a billing for professional tax consulting services. The amount is substantial, and the invoice date is provided, which adds to the context. However, the supplier profile is not available, which limits the ability to assess the supplier's context. Given that ""kpmg llp"" is a well-known professional services firm, it is likely that research would yield useful information about their services and industry. Therefore, research is warranted to gain a better understanding of the supplier's context. [Invoice-level assessment: 5 line items]",
`

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

  // Parse CSV helper function
  const parseCSV = (csvText) => {
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
  }

  // Parse a single CSV line handling quoted fields
  const parseCSVLine = (line) => {
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
  }

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

  // Load hard-coded CSV rows on component mount
  useEffect(() => {
    setLoading(true)
    try {
      const rows = parseCSV(HARD_CODED_CSV)
        setResults(rows)
    } catch (err) {
      setError(`Failed to parse CSV: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [])

  // Load feedback on component mount
  useEffect(() => {
    loadFeedback()
  }, [loadFeedback])


  const handleOpenFeedback = () => {
    if (selectedRows.length === 0) {
      setError('Please select at least one row to provide feedback')
      return
    }
    setFeedbackModal({
      rows: selectedRows,
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
      
      await axios.post(`${API_BASE}/feedback/${feedbackId}/apply`, {
        row_indices: [rowIndex]
      }, {
        headers: {
          'accept': 'application/json',
          'Content-Type': 'application/json'
        }
      })
      
      setSuccess(`Feedback #${feedbackId} applied successfully!`)
      
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

    // Add a selection checkbox column to make row selection obvious
    return [
      {
        colId: '__select__',
        headerName: '',
        checkboxSelection: true,
        headerCheckboxSelection: true,
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
    if (gridApiRef.current && gridApiRef.current.autoSizeAllColumns) {
      gridApiRef.current.autoSizeAllColumns()
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
    setSelectedRows(selected)
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
          <label>File</label>
          <div style={{ padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, background: '#f9fafb', minWidth: 260 }}>
            <div style={{ fontWeight: 600 }}>classified.csv</div>
          </div>
        </div>

        <div className="control-group">
          <label>Selected Rows</label>
          <input type="text" value={selectedRows.length} readOnly style={{ width: '80px' }} />
        </div>

        <button className="btn btn-primary" onClick={handleOpenFeedback} disabled={selectedRows.length === 0}>
          Provide Feedback ({selectedRows.length})
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
                rowSelection="multiple"
                rowMultiSelectWithClick={true}
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
      <div style={{ marginTop: '30px', borderTop: '2px solid #e0e0e0', paddingTop: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <h2 style={{ margin: 0 }}>Submitted Feedback</h2>
          <button 
            className="btn btn-secondary" 
            onClick={loadFeedback}
            disabled={loadingFeedback}
            style={{ fontSize: '14px', padding: '6px 12px' }}
          >
            {loadingFeedback ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        {loadingFeedback && feedbackItems.length === 0 ? (
          <div className="loading">Loading feedback...</div>
        ) : feedbackItems.length === 0 ? (
          <div style={{ padding: '20px', textAlign: 'center', color: '#666' }}>
            No feedback submitted yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
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
                    border: '1px solid #ddd',
                    borderRadius: '8px',
                    padding: '15px',
                    background: '#fff',
                    cursor: 'pointer',
                    transition: 'all 0.2s'
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
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                        <span style={{ 
                          fontWeight: 'bold', 
                          fontSize: '16px',
                          color: '#333'
                        }}>
                          Feedback #{feedback.id}
                        </span>
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '12px',
                          fontWeight: '600',
                          background: statusColor + '20',
                          color: statusColor
                        }}>
                          {feedback.status?.toUpperCase() || 'UNKNOWN'}
                        </span>
                      </div>
                      <div style={{ fontSize: '14px', color: '#666', marginBottom: '4px' }}>
                        <strong>Row {feedback.row_index}</strong> • Dataset: {feedback.dataset_id}
                      </div>
                      <div style={{ fontSize: '13px', color: '#555', marginTop: '8px' }}>
                        <div style={{ marginBottom: '4px' }}>
                          <span style={{ color: '#999' }}>Original: </span>
                          <span style={{ color: '#dc2626' }}>{feedback.original_classification || 'N/A'}</span>
                        </div>
                        <div>
                          <span style={{ color: '#999' }}>Corrected: </span>
                          <span style={{ color: '#16a34a' }}>{feedback.corrected_classification || 'N/A'}</span>
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
                              padding: '6px 12px',
                              background: '#10b981',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: loading ? 'not-allowed' : 'pointer'
                            }}
                          >
                            {loading ? 'Approving...' : 'Approve'}
                          </button>
                          <button
                            onClick={(e) => handleDeleteFeedback(feedback.id, e)}
                            disabled={loading}
                            style={{ 
                              fontSize: '16px', 
                              padding: '6px 10px',
                              background: 'transparent',
                              color: '#dc2626',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: loading ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center'
                            }}
                            title="Delete feedback"
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
                            padding: '6px 12px',
                            background: '#3b82f6',
                            color: 'white',
                            border: 'none',
                            borderRadius: '4px',
                            cursor: loading ? 'not-allowed' : 'pointer'
                          }}
                        >
                          {loading ? 'Applying...' : 'Apply'}
                        </button>
                      )}
                      <div style={{ fontSize: '20px', color: '#999', marginLeft: '5px' }}>
                        {isExpanded ? '▼' : '▶'}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div style={{ 
                      marginTop: '15px', 
                      paddingTop: '15px', 
                      borderTop: '1px solid #e5e7eb',
                      fontSize: '14px'
                    }}>
                      {feedback.feedback_text && (
                        <div style={{ marginBottom: '12px' }}>
                          <strong style={{ color: '#374151' }}>Feedback Text:</strong>
                          <div style={{ marginTop: '4px', padding: '8px', background: '#f9fafb', borderRadius: '4px', whiteSpace: 'pre-wrap' }}>
                            {feedback.feedback_text}
                          </div>
                        </div>
                      )}

                      {feedback.action_reasoning && (
                        <div style={{ marginBottom: '12px' }}>
                          <strong style={{ color: '#374151' }}>Action Reasoning:</strong>
                          <div style={{ marginTop: '4px', padding: '8px', background: '#f9fafb', borderRadius: '4px', whiteSpace: 'pre-wrap', lineHeight: '1.5' }}>
                            {feedback.action_reasoning}
                          </div>
                        </div>
                      )}

                      {feedback.proposal_text && (
                        <div style={{ marginBottom: '12px' }}>
                          <strong style={{ color: '#374151' }}>Proposal:</strong>
                          <div style={{ marginTop: '4px', padding: '8px', background: '#eff6ff', borderRadius: '4px', whiteSpace: 'pre-wrap', lineHeight: '1.5' }}>
                            {feedback.proposal_text}
                          </div>
                        </div>
                      )}

                      {feedback.created_at && (
                        <div style={{ fontSize: '12px', color: '#6b7280', marginTop: '12px' }}>
                          <strong>Created:</strong> {new Date(feedback.created_at).toLocaleString()}
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



