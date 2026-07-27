import { QuantifayaHeader } from '@/components/layout/QuantifayaHeader'

export function GraphExplorer() {
  return (
    <div className="flex h-screen flex-col bg-background">
      <QuantifayaHeader />
      <div className="flex flex-1 items-center justify-center p-8">
        <div className="max-w-lg rounded-xl border border-border bg-surface p-8 text-center shadow-lg">
          <div className="mb-4 text-4xl">🕸️</div>
          <h2
            className="mb-2 text-2xl font-bold text-text-primary"
            style={{ fontFamily: 'Raleway, sans-serif', fontWeight: 700 }}
          >
            Graph Explorer
          </h2>
          <p className="text-text-secondary">
            Interactive causal graph visualisation — coming on <strong className="text-risk-green">Day 4</strong>.
          </p>
          <p className="mt-2 text-sm text-text-muted">
            This view will display the VARLiNGAM causal network with
            force-directed layout, edge weights, and causal chains.
            Regions will be colour-coded by risk score with selectable
            nodes for detailed inspection.
          </p>
        </div>
      </div>
    </div>
  )
}