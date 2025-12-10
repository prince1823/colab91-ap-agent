import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import axios from 'axios'
import FeedbackModal from './FeedbackModal'
import './App.css'

const API_BASE = '/api'

function App() {
  const gridApiRef = useRef(null)
  const [results, setResults] = useState([])
  const [resultFiles, setResultFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [feedbackModal, setFeedbackModal] = useState(null)
  const [selectedRows, setSelectedRows] = useState([])
  const [iteration, setIteration] = useState(0)
  const [feedbackStats, setFeedbackStats] = useState({
    total: 0,
    correct: 0,
    incorrect: 0,
    corrections: 0,
  })
  const [canonicalColumns, setCanonicalColumns] = useState([])
  const [columnOverrides, setColumnOverrides] = useState({})

  // Load result files on mount
  useEffect(() => {
    loadResultFiles()
    loadCanonicalColumns()
  }, [])

  // Load results when file is selected
  useEffect(() => {
    if (selectedFile) {
      loadResults(selectedFile)
      loadFeedback(selectedFile)
      extractIteration(selectedFile)
    }
  }, [selectedFile])

  const loadResultFiles = async () => {
    try {
      const response = await axios.get(`${API_BASE}/results`)
      setResultFiles(response.data.results || [])
      if (response.data.results && response.data.results.length > 0) {
        setSelectedFile(response.data.results[0].filename)
      }
    } catch (err) {
      setError(`Failed to load result files: ${err.message}`)
    }
  }

  const loadCanonicalColumns = async () => {
    try {
      const response = await axios.get(`${API_BASE}/canonical-columns`)
      const cols = response.data.columns || []
      setCanonicalColumns(cols)
      setColumnOverrides((prev) => {
        const next = { ...prev }
        cols.forEach((col) => {
          if (!next[col.canonical_name]) {
            next[col.canonical_name] = col.canonical_name
          }
        })
        return next
      })
    } catch (err) {
      setError(`Failed to load canonical columns: ${err.message}`)
    }
  }

  const [pageOffset, setPageOffset] = useState(0)
  const pageLimit = 500
  const [totalRows, setTotalRows] = useState(0)

  const loadResultsPage = async (filename, offset = 0, append = false) => {
    setLoading(true)
    setError(null)
    try {
      const response = await axios.get(`${API_BASE}/results/${filename}/page`, {
        params: { offset, limit: pageLimit },
      })
      const data = response.data
      const rows = data.data || []
      setTotalRows(data.total_rows || rows.length)
      if (append) {
        setResults((prev) => [...prev, ...rows])
      } else {
        setResults(rows)
      }
      setPageOffset(offset + rows.length)
    } catch (err) {
      setError(`Failed to load results: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const loadResults = (filename) => loadResultsPage(filename, 0, false)

  const loadFeedback = async (filename) => {
    try {
      const response = await axios.get(`${API_BASE}/feedback/${filename}`)
      const batches = response.data.feedback_batches || []
      let stats = { total: 0, correct: 0, incorrect: 0, corrections: 0 }
      
      batches.forEach(batch => {
        batch.feedback_items.forEach(item => {
          stats.total++
          if (item.feedback_type === 'correct') stats.correct++
          else if (item.feedback_type === 'incorrect') stats.incorrect++
          else if (item.feedback_type === 'correction') stats.corrections++
        })
      })
      
      setFeedbackStats(stats)
    } catch (err) {
      // No feedback yet is okay
      setFeedbackStats({ total: 0, correct: 0, incorrect: 0, corrections: 0 })
    }
  }

  const extractIteration = (filename) => {
    const match = filename.match(/iter(\d+)/)
    if (match) {
      setIteration(parseInt(match[1]) + 1) // Next iteration
    } else {
      setIteration(1)
    }
  }

  const handleOpenFeedback = () => {
    if (selectedRows.length === 0) {
      setError('Please select at least one row to provide feedback')
      return
    }
    setFeedbackModal({
      rows: selectedRows,
      filename: selectedFile,
      iteration: iteration - 1, // Current iteration
    })
  }

  const handleSubmitFeedback = async (feedbackData) => {
    try {
      const response = await axios.post(`${API_BASE}/feedback`, feedbackData)
      setSuccess(`Feedback submitted successfully! ${response.data.items_count} items saved.`)
      setFeedbackModal(null)
      setSelectedRows([])
      loadFeedback(selectedFile)
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(`Failed to submit feedback: ${err.message}`)
    }
  }

  const handleRunWithFeedback = async () => {
    if (!selectedFile) {
      setError('Please select a result file first')
      return
    }

    setLoading(true)
    setError(null)
    try {
      const overridesPayload = {}
      canonicalColumns.forEach((col) => {
        const value = columnOverrides[col.canonical_name]
        if (value && value.trim() && value.trim() !== col.canonical_name) {
          overridesPayload[col.canonical_name] = value.trim()
        }
      })

      // Extract input file and taxonomy from the result file
      // This is a simplified version - you might want to store this metadata
      const response = await axios.post(`${API_BASE}/run`, {
        input_file: `results/${selectedFile}`, // Adjust based on your structure
        taxonomy_path: 'taxonomies/FOX_20230816_161348.yaml', // You might want to make this configurable
        iteration: iteration,
        use_feedback: true,
        normalized_column_overrides: Object.keys(overridesPayload).length ? overridesPayload : undefined,
      })

      setSuccess(`Pipeline run completed! New iteration: ${response.data.iteration}`)
      setTimeout(() => {
        loadResultFiles()
      }, 1000)
    } catch (err) {
      setError(`Failed to run pipeline: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const columnDefs = useMemo(() => {
    if (results.length === 0) return []
    
    const cols = Object.keys(results[0]).map(key => ({
      field: key,
      headerName: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      sortable: true,
      filter: true,
      resizable: true,
      minWidth: 140,
    }))

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

  const handleOverrideChange = (canonicalName, value) => {
    setColumnOverrides((prev) => ({
      ...prev,
      [canonicalName]: value,
    }))
  }

  const resetOverrides = () => {
    setColumnOverrides((prev) => {
      const next = { ...prev }
      canonicalColumns.forEach((col) => {
        next[col.canonical_name] = col.canonical_name
      })
      return next
    })
  }

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
          <label>Result File</label>
          <select value={selectedFile} onChange={(e) => setSelectedFile(e.target.value)}>
            <option value="">Select a file...</option>
            {resultFiles.map(file => (
              <option key={file.filename} value={file.filename}>
                {file.filename} ({file.row_count} rows, Iteration {file.iteration})
              </option>
            ))}
          </select>
        </div>

        <div className="control-group">
          <label>Selected Rows</label>
          <input type="text" value={selectedRows.length} readOnly style={{ width: '80px' }} />
        </div>

        <button className="btn btn-primary" onClick={handleOpenFeedback} disabled={selectedRows.length === 0}>
          Provide Feedback ({selectedRows.length})
        </button>

        <button className="btn btn-success" onClick={handleRunWithFeedback} disabled={!selectedFile || loading}>
          {loading ? 'Running...' : `Run Next Iteration (${iteration})`}
        </button>

        <button className="btn btn-secondary" onClick={loadResultFiles}>
          Refresh Files
        </button>
      </div>

      {canonicalColumns.length > 0 && (
        <div className="override-panel">
          <div className="override-header">
            <div>
              <strong>Normalized column names</strong>
              <div className="override-helper">
                Adjust how canonicalized columns are labeled in the output. Leave blank to use defaults.
              </div>
            </div>
            <button className="btn btn-secondary" onClick={resetOverrides}>
              Reset to defaults
            </button>
          </div>
          <div className="override-grid">
            {canonicalColumns.map((col) => (
              <div className="override-row" key={col.canonical_name}>
                <div className="override-label">
                  <div className="override-name">{col.canonical_name}</div>
                  <div className="override-meta">
                    {col.relevance_for_spend_analysis} • {col.data_type}
                  </div>
                </div>
                <input
                  type="text"
                  value={columnOverrides[col.canonical_name] ?? ''}
                  onChange={(e) => handleOverrideChange(col.canonical_name, e.target.value)}
                  placeholder={col.canonical_name}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {feedbackStats.total > 0 && (
        <div className="feedback-panel">
          <h3>Feedback Statistics</h3>
          <div className="feedback-stats">
            <div className="stat-card">
              <div className="stat-value">{feedbackStats.total}</div>
              <div className="stat-label">Total Feedback</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: '#28a745' }}>{feedbackStats.correct}</div>
              <div className="stat-label">Correct</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: '#dc3545' }}>{feedbackStats.incorrect}</div>
              <div className="stat-label">Incorrect</div>
            </div>
            <div className="stat-card">
              <div className="stat-value" style={{ color: '#ffc107' }}>{feedbackStats.corrections}</div>
              <div className="stat-label">Corrections</div>
            </div>
          </div>
        </div>
      )}

      <div className="grid-container">
        {loading ? (
          <div className="loading">Loading results...</div>
        ) : results.length === 0 ? (
          <div className="loading">No results loaded. Select a file above.</div>
        ) : (
          <>
            <div style={{ marginBottom: 10, fontSize: 12, color: '#555' }}>
              Showing {results.length} of {totalRows || results.length} rows
              {totalRows > results.length && (
                <span style={{ marginLeft: 8 }}>
                  (load more to see additional rows)
                </span>
              )}
            </div>
            <div className="ag-theme-alpine" style={{ height: '600px', width: '100%' }}>
              <AgGridReact
                rowData={rowData}
                columnDefs={columnDefs}
                defaultColDef={defaultColDef}
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
            {results.length < totalRows && (
              <div style={{ marginTop: 10 }}>
                <button
                  className="btn btn-secondary"
                  onClick={() => loadResultsPage(selectedFile, pageOffset, true)}
                  disabled={loading}
                >
                  {loading ? 'Loading...' : `Load next ${pageLimit} rows`}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {feedbackModal && (
        <FeedbackModal
          modal={feedbackModal}
          onClose={() => setFeedbackModal(null)}
          onSubmit={handleSubmitFeedback}
        />
      )}
    </div>
  )
}

export default App

