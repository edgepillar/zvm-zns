import {dirname} from 'node:path'
import normalConfiguration from '../../web/vite.config.ts'
import {distributionObserver} from './distribution-observer.mjs'

export default async function configuration(environment) {
  const config = await normalConfiguration(environment)
  const observer = distributionObserver(dirname(process.cwd()), process.env.ZNS_DISTRIBUTION_EVIDENCE)
  return {...config, plugins: [...config.plugins, observer]}
}
