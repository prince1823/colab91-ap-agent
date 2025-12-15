import React, { useState } from 'react'
import { AgGridReact } from 'ag-grid-react'
import 'ag-grid-community/styles/ag-grid.css'
import 'ag-grid-community/styles/ag-theme-alpine.css'

function BulkChangeModal({ 
  applicableRows, 
  actionProposal, 
  onClose, 
  onApprove, 
  onReject, 
  loading = false 
}) {
  const [selectedRows, setSelectedRows] = useState([])

  const columnDefs = React.useMemo(() => {
    if (applicableRows.length === 0) return []
    
    return Object.keys(applicableRows[0]).map(key => ({
      field: key,
      headerName: key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
      sortable: true,
      filter: true,
      resizable: true,
      minWidth: 140,
    }))
  }, [applicableRows])

  const getActionTypeLabel = (type) => {
    const labels = {
      taxonomy_update: 'Taxonomy Update',
      user_context_update: 'User Context Update',
      supplier_db_update: 'Supplier Database Update',
      rule_creation: 'Rule Creation',
    }
    return labels[type] || type
  }

  const onSelectionChanged = (event) => {
    const selected = event.api.getSelectedRows()
    setSelectedRows(selected)
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal bulk-change-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '90vw', width: '1200px' }}>
        <h2>Review Bulk Changes</h2>
        
        <div className="bulk-change-info">
          <div className="info-section">
            <label>Action Type:</label>
            <span className="action-type-badge">{getActionTypeLabel(actionProposal.action_type)}</span>
          </div>
          
          <div className="info-section">
            <label>Proposed Change:</label>
            <p className="proposed-change-text">{actionProposal.proposal_text || actionProposal.proposed_change || actionProposal.action_details?.proposed_change || 'No change text available'}</p>
          </div>
          
          <div className="info-section">
            <label>Affected Rows:</label>
            <span className="row-count">{applicableRows.length} rows will be updated</span>
          </div>
        </div>

        <div style={{ marginBottom: '20px' }}>
          <h3>Preview of Affected Rows:</h3>
          <div className="ag-theme-alpine" style={{ height: '400px', width: '100%' }}>
            <AgGridReact
              rowData={applicableRows}
              columnDefs={columnDefs}
              rowSelection="multiple"
              onSelectionChanged={onSelectionChanged}
              pagination={true}
              paginationPageSize={50}
              defaultColDef={{
                sortable: true,
                filter: true,
                resizable: true,
              }}
            />
          </div>
        </div>

        <div className="modal-actions">
          <button 
            className="btn btn-secondary" 
            onClick={onReject}
            disabled={loading}
          >
            Reject Changes
          </button>
          <button 
            className="btn btn-primary" 
            onClick={() => onApprove(actionProposal)}
            disabled={loading}
          >
            {loading ? 'Applying...' : `Approve & Apply to ${applicableRows.length} Rows`}
          </button>
        </div>
      </div>
    </div>
  )
}

export default BulkChangeModal
