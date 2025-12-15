import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'
import axios from 'axios'
import FeedbackModal from './FeedbackModal'
import ProposalModal from './ProposalModal'
import BulkChangeModal from './BulkChangeModal'
import './App.css'

const API_BASE = 'http://localhost:8000/api'
const DEFAULT_RESULT_FILE = 'classified.csv'
const DEFAULT_TAXONOMY_FILE = 'FOX_20230816_161348.yaml'

function App() {
  const gridApiRef = useRef(null)
  const [results, setResults] = useState([])
  const [selectedFile, setSelectedFile] = useState(DEFAULT_RESULT_FILE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(null)
  const [feedbackModal, setFeedbackModal] = useState(null)
  const [proposalModal, setProposalModal] = useState(null)
  const [bulkChangeModal, setBulkChangeModal] = useState(null)
  const [selectedRows, setSelectedRows] = useState([])
  const [processingFeedback, setProcessingFeedback] = useState(false)
  const [iteration, setIteration] = useState(0)
  const [feedbackStats, setFeedbackStats] = useState({
    total: 0,
    correct: 0,
    incorrect: 0,
    corrections: 0,
  })
  const [canonicalColumns, setCanonicalColumns] = useState([])
  const [columnOverrides, setColumnOverrides] = useState({})
  const [savingOverrides, setSavingOverrides] = useState(false)
  const [overrideRules, setOverrideRules] = useState([])
  const [loadingRules, setLoadingRules] = useState(false)

  const syncCanonicalColumns = useCallback((cols, overridesFromServer = {}) => {
    setCanonicalColumns(cols)
    setColumnOverrides((prev) => {
      const next = { ...prev }
      cols.forEach((col) => {
        const incoming = overridesFromServer[col.canonical_name]
        if (typeof incoming === 'string' && incoming.trim()) {
          next[col.canonical_name] = incoming.trim()
        } else if (!next[col.canonical_name]) {
          next[col.canonical_name] = col.canonical_name
        }
      })
      return next
    })
  }, [])

  const loadCanonicalColumns = useCallback(async () => {
    try {
      const response = await axios.get(`${API_BASE}/normalized-column-overrides`)
      const cols = response.data.columns || []
      const overridesFromServer = response.data.overrides || {}
      syncCanonicalColumns(cols, overridesFromServer)
    } catch (primaryErr) {
      try {
        const response = await axios.get(`${API_BASE}/canonical-columns`)
        const cols = response.data.columns || []
        const overridesFromServer = response.data.overrides || {}
        syncCanonicalColumns(cols, overridesFromServer)
      } catch (fallbackErr) {
        setError(`Failed to load canonical columns: ${fallbackErr.message || fallbackErr}`)
      }
    }
  }, [syncCanonicalColumns])

  const loadOverrideRules = useCallback(async () => {
    setLoadingRules(true)
    try {
      const response = await axios.get(`${API_BASE}/taxonomy/${DEFAULT_TAXONOMY_FILE}/override-rules`)
      setOverrideRules(response.data.override_rules || [])
    } catch (err) {
      setError(`Failed to load override rules: ${err.message}`)
    } finally {
      setLoadingRules(false)
    }
  }, [])

  useEffect(() => {
    loadCanonicalColumns()
    loadOverrideRules()
  }, [loadCanonicalColumns, loadOverrideRules])

  useEffect(() => {
    if (selectedFile) {
      loadResults(selectedFile)
      loadFeedback(selectedFile)
      extractIteration(selectedFile)
    }
  }, [selectedFile])

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
      
      // Process first feedback item to generate proposal
      if (feedbackData.feedback_items && feedbackData.feedback_items.length > 0) {
        await processFeedbackItem(0, feedbackData.result_file)
      }
      
      setTimeout(() => setSuccess(null), 5000)
    } catch (err) {
      setError(`Failed to submit feedback: ${err.message}`)
    }
  }

  const processFeedbackItem = async (itemIndex, resultFile) => {
    setProcessingFeedback(true)
    setError(null)
    try {
      const response = await axios.post(`${API_BASE}/feedback/process`, {
        result_file: resultFile,
        feedback_item_index: itemIndex,
      })
      
      setProposalModal({
        proposal: response.data,
        feedbackItemIndex: itemIndex,
        resultFile: resultFile,
      })
    } catch (err) {
      setError(`Failed to process feedback: ${err.message}`)
    } finally {
      setProcessingFeedback(false)
    }
  }

  const handleApproveProposal = async (editedText) => {
    setProcessingFeedback(true)
    setError(null)
    try {
      const response = await axios.post(`${API_BASE}/feedback/approve`, {
        result_file: proposalModal.resultFile,
        feedback_item_index: proposalModal.feedbackItemIndex,
        action_proposal: proposalModal.proposal,
        edited_text: editedText,
      })
      
      setProposalModal(null)
      
      // If bulk approval needed, show bulk change modal
      if (response.data.requires_bulk_approval && response.data.applicable_rows) {
        setBulkChangeModal({
          applicableRows: response.data.applicable_rows,
          actionProposal: proposalModal.proposal,
          resultFile: proposalModal.resultFile,
          executionResult: response.data.execution_result,
        })
      } else {
        setSuccess('Action approved and executed successfully!')
        setTimeout(() => setSuccess(null), 5000)
      }
    } catch (err) {
      setError(`Failed to approve action: ${err.message}`)
    } finally {
      setProcessingFeedback(false)
    }
  }

  const handleRejectProposal = () => {
    setProposalModal(null)
  }

  const handleApproveBulkChanges = async (actionProposal) => {
    setProcessingFeedback(true)
    setError(null)
    try {
      const response = await axios.post(`${API_BASE}/feedback/apply-bulk`, {
        result_file: bulkChangeModal.resultFile,
        action_proposal: actionProposal,
        approved: true,
      })
      
      setBulkChangeModal(null)
      setSuccess(`Bulk changes applied successfully! ${response.data.rows_updated} rows updated. New file: ${response.data.updated_file}`)
      setTimeout(() => {
        setSuccess(null)
        if (response.data.updated_file) {
          setSelectedFile(response.data.updated_file)
        } else if (selectedFile) {
          loadResults(selectedFile)
        }
      }, 5000)
    } catch (err) {
      setError(`Failed to apply bulk changes: ${err.message}`)
    } finally {
      setProcessingFeedback(false)
    }
  }

  const handleRejectBulkChanges = () => {
    setBulkChangeModal(null)
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
          taxonomy_path: `taxonomies/${DEFAULT_TAXONOMY_FILE}`, // You might want to make this configurable
        iteration: iteration,
        use_feedback: true,
        normalized_column_overrides: Object.keys(overridesPayload).length ? overridesPayload : undefined,
      })

      setSuccess(`Pipeline run completed! New iteration: ${response.data.iteration}`)
      setTimeout(() => {
        if (response.data.output_file) {
          setSelectedFile(response.data.output_file)
        } else if (selectedFile) {
          loadResults(selectedFile)
        }
      }, 1000)
    } catch (err) {
      setError(`Failed to run pipeline: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const columnDefs = useMemo(() => {
    if (results.length === 0) return []

    const toHeader = (key) => {
      const overrideName = columnOverrides[key]
      if (overrideName && typeof overrideName === 'string' && overrideName.trim()) {
        return overrideName.trim()
      }
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
          autoHeight: true,
          wrapText: true,
          cellStyle: { whiteSpace: 'pre-wrap', lineHeight: 1.4 },
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
  }, [results, columnOverrides])

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

  const handleSaveOverrides = async () => {
    setSavingOverrides(true)
    try {
      const payload = {}
      canonicalColumns.forEach((col) => {
        const value = columnOverrides[col.canonical_name]
        payload[col.canonical_name] = value && value.trim() ? value.trim() : col.canonical_name
      })

      await axios.post(`${API_BASE}/normalized-column-overrides`, { overrides: payload })
      setSuccess('Normalized column names saved')
      setTimeout(() => setSuccess(null), 4000)
    } catch (err) {
      setError(`Failed to save normalized column names: ${err.message}`)
    } finally {
      setSavingOverrides(false)
    }
  }

  const handleDeleteRule = async (ruleIndex) => {
    setLoadingRules(true)
    try {
      await axios.delete(`${API_BASE}/taxonomy/${DEFAULT_TAXONOMY_FILE}/override-rules/${ruleIndex}`)
      setSuccess('Rule deleted from taxonomy')
      loadOverrideRules()
      setTimeout(() => setSuccess(null), 4000)
    } catch (err) {
      setError(`Failed to delete rule: ${err.message}`)
    } finally {
      setLoadingRules(false)
    }
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
          <div style={{ padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, background: '#f9fafb', minWidth: 260 }}>
            <div style={{ fontWeight: 600 }}>{selectedFile}</div>
            <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>Using bundled classified.csv</div>
          </div>
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
      </div>

      <div className="override-panel">
        <div className="override-header">
          <div>
            <strong>Override rules</strong>
            <div className="override-helper">
              Manage classification override rules saved in the taxonomy file.
            </div>
          </div>
          <div className="override-actions">
            <button className="btn btn-secondary" onClick={loadOverrideRules} disabled={loadingRules}>
              {loadingRules ? 'Refreshing...' : 'Refresh rules'}
            </button>
          </div>
        </div>
        {overrideRules.length === 0 ? (
          <div className="override-helper">No override rules saved yet.</div>
        ) : (
          <div className="override-grid">
            {overrideRules.map((rule) => (
              <div
                key={rule.index}
                className="override-row"
                style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}
              >
                <div className="override-label" style={{ flex: 1 }}>
                  <div className="override-name">Rule #{rule.index + 1}</div>
                  <div className="override-meta" style={{ whiteSpace: 'pre-wrap' }}>
                    {rule.rule}
                  </div>
                </div>
                <button
                  className="btn btn-secondary"
                  style={{ background: '#fef2f2', color: '#c0392b', borderColor: '#f5c6cb' }}
                  onClick={() => handleDeleteRule(rule.index)}
                  disabled={loadingRules}
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

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

      {proposalModal && (
        <ProposalModal
          proposal={proposalModal.proposal}
          onClose={handleRejectProposal}
          onApprove={handleApproveProposal}
          onReject={handleRejectProposal}
          loading={processingFeedback}
        />
      )}

      {bulkChangeModal && (
        <BulkChangeModal
          applicableRows={bulkChangeModal.applicableRows}
          actionProposal={bulkChangeModal.actionProposal}
          onClose={handleRejectBulkChanges}
          onApprove={handleApproveBulkChanges}
          onReject={handleRejectBulkChanges}
          loading={processingFeedback}
        />
      )}
    </div>
  )
}

export default App

