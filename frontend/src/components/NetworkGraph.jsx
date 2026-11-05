import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { hideUnlinked, toElements } from '../services/graphElements.js';

const STYLE = [
  {
    selector: 'node',
    style: {
      'background-color': 'data(color)',
      shape: 'data(platformShape)',
      label: 'data(label)',
      color: '#0f172a',
      'font-family': 'Poppins, sans-serif',
      'font-size': 11,
      'text-valign': 'bottom',
      'text-margin-y': 5,
      'min-zoomed-font-size': 8,
      width: 26,
      height: 26,
      'border-width': 2,
      'border-color': '#ffffff',
    },
  },
  {
    selector: 'edge',
    style: {
      width: 'data(width)',
      'line-color': '#cbd5e1',
      'curve-style': 'straight',
    },
  },
  { selector: 'node[?checked]', style: { 'border-color': '#ea580c', 'border-width': 4, width: 34, height: 34 } },
  { selector: 'node:selected', style: { 'border-color': '#0f172a', 'border-width': 3 } },
  { selector: 'edge:selected', style: { 'line-color': '#0f172a' } },
];

// Each edge's thickness reflects how many signals it has; its evidence is
// reported through onSelect so the page can show it.
export default function NetworkGraph({ graph, onSelect }) {
  const containerRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  const [showUnlinked, setShowUnlinked] = useState(false);
  const { graph: linkedOnly, hiddenCount } = useMemo(() => hideUnlinked(graph), [graph]);
  const shown = showUnlinked ? graph : linkedOnly;

  const { elements, droppedEdges } = useMemo(() => toElements(shown), [shown]);
  const isEmpty = elements.length === 0;

  useEffect(() => {
    if (isEmpty) return undefined;
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: STYLE,
      layout: {
        name: 'cose',
        animate: false,
        nodeDimensionsIncludeLabels: true,
        nodeRepulsion: () => 60000,
        idealEdgeLength: () => 110,
        componentSpacing: 60,
        padding: 24,
      },
      wheelSensitivity: 0.3,
      maxZoom: 3,
      minZoom: 0.1,
    });
    cy.on('tap', 'node, edge', (event) => {
      const element = event.target;
      onSelectRef.current({ kind: element.isNode() ? 'node' : 'edge', item: element.data('raw') });
    });
    cy.on('tap', (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });
    return () => cy.destroy();
  }, [elements, isEmpty]);

  if (isEmpty) {
    return (
      <div className="graph-empty">
        <p>No accounts or relationships to show.</p>
        <p className="muted small">Import a dataset with valid records to build a graph.</p>
      </div>
    );
  }

  return (
    <>
      <div
        ref={containerRef}
        className="graph-canvas"
        role="img"
        aria-label={`Network graph of ${shown.nodes.length} accounts. Evidence for each relationship appears in the panel beside it.`}
      />
      {hiddenCount > 0 && (
        <p className="graph-note small">
          {showUnlinked ? (
            'Showing all accounts, including those with no observed links.'
          ) : (
            <>
              {hiddenCount === 1 ? '1 account with no observed links is' : `${hiddenCount} accounts with no observed links are`}{' '}
              hidden from the graph. Their posts are still in the table below.
            </>
          )}{' '}
          <button
            type="button"
            className="link-button"
            onClick={() => {
              setShowUnlinked(!showUnlinked);
              onSelect(null);
            }}
          >
            {showUnlinked ? 'Hide them' : 'Show them'}
          </button>
        </p>
      )}
      {droppedEdges > 0 && (
        <p className="notice notice-error small">
          {droppedEdges} relationships weren't drawn because they refer to accounts missing from the graph.
        </p>
      )}
    </>
  );
}
