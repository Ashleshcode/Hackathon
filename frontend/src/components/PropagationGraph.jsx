import { useEffect, useMemo, useRef } from 'react';
import cytoscape from 'cytoscape';
import { toPropagationElements } from '../services/propagationElements.js';

const STYLE = [
  {
    selector: 'node',
    style: {
      'background-color': '#dbeafe',
      label: 'data(label)',
      color: '#0f172a',
      'font-family': 'IBM Plex Mono, ui-monospace, monospace',
      'font-size': 10,
      'text-valign': 'bottom',
      'text-margin-y': 6,
      width: 22,
      height: 22,
      'border-width': 2,
      'border-color': '#1d4ed8',
    },
  },
  {
    selector: 'node[?isRoot]',
    style: { 'background-color': '#1d4ed8', color: '#1d4ed8', width: 28, height: 28 },
  },
  {
    selector: 'edge',
    style: {
      width: 1.5,
      'line-color': '#64748b',
      'target-arrow-color': '#64748b',
      'target-arrow-shape': 'triangle',
      'curve-style': 'bezier',
    },
  },
  { selector: 'node:selected, edge:selected', style: { 'border-color': '#0f172a', 'line-color': '#0f172a', 'target-arrow-color': '#0f172a' } },
];

export default function PropagationGraph({ graph, onSelect }) {
  const containerRef = useRef(null);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const { elements, rootIds } = useMemo(() => toPropagationElements(graph), [graph]);

  useEffect(() => {
    if (elements.length === 0) return undefined;
    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: STYLE,
      layout: {
        name: 'breadthfirst',
        directed: true,
        roots: rootIds,
        spacingFactor: 1.25,
        animate: false,
        padding: 24,
      },
      wheelSensitivity: 0.3,
    });
    cy.on('tap', 'node, edge', (event) => {
      const element = event.target;
      onSelectRef.current({ kind: element.isNode() ? 'node' : 'edge', item: element.data('raw') });
    });
    cy.on('tap', (event) => {
      if (event.target === cy) onSelectRef.current(null);
    });
    return () => cy.destroy();
  }, [elements, rootIds]);

  if (elements.length === 0) {
    return (
      <div className="graph-empty">
        <p>This case has no propagation nodes.</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="graph-canvas"
      role="img"
      aria-label="Directional propagation tree. Arrows point from the parent post to the child post."
    />
  );
}
